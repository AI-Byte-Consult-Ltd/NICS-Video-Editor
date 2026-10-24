"""Site job worker: polls the jobs API for queued uploads, runs pipeline.py on
them and sends the results back. Needs only outbound HTTPS, so it can run on
the workstation or on a server.

All calls go to NICS_VIDEO_API_BASE (the n8n webhook base URL) with
"Authorization: Bearer $NICS_VIDEO_WORKER_TOKEN". Files travel in parts of at
most PART_SIZE bytes, so no single request exceeds the webhook body limit.
  POST nics-video-worker {"action": "claim"}
       -> {"job": null} or {"job": {"id", "name", "title", "title_en", "long_duration",
           "short_duration", "inputs": [{"index", "filename", "parts"}]}}
  POST nics-video-worker {"action": "progress", "job_id", "stage"}
  POST nics-video-worker {"action": "complete", "job_id", "files": [{"name", "size", "parts"}]}
  POST nics-video-worker {"action": "fail", "job_id", "error"}
  GET  nics-video-worker-file?job=ID&file=INDEX&part=N      -> raw bytes of one input part
  POST nics-video-worker-upload?job=ID&name=NAME&part=N      body: raw bytes of one output part

Usage:
  python worker.py            # loop forever
  python worker.py --once     # handle at most one job, then exit
"""
import argparse
import os
import re
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import requests

from config import ROOT, SUPPORTED_EXTENSIONS
import pipeline

API_BASE = os.environ.get("NICS_VIDEO_API_BASE", "https://n8n.aibyteconsult.com/webhook").rstrip("/")
TOKEN = os.environ.get("NICS_VIDEO_WORKER_TOKEN", "")
POLL_SECONDS = float(os.environ.get("NICS_VIDEO_POLL_SECONDS", "15"))
PART_SIZE = 8 * 1024 * 1024
WORK_DIR = os.path.join(ROOT, "work")


def _headers(**extra):
    return {"Authorization": f"Bearer {TOKEN}", **extra}


def _request(method, path, retries=4, **kwargs):
    """Retries network errors and 5xx with backoff: a laptop on Wi-Fi drops."""
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, f"{API_BASE}/{path}", **kwargs)
            if r.status_code < 500:
                r.raise_for_status()
                return r
            err = requests.HTTPError(f"{r.status_code} {r.text[:200]}")
        except (requests.ConnectionError, requests.Timeout) as e:
            err = e
        if attempt == retries:
            raise err
        time.sleep(2 ** (attempt + 1))


def call(action, **payload):
    r = _request("POST", "nics-video-worker", json={"action": action, **payload},
                 headers=_headers(), timeout=60)
    return r.json() if r.content else {}


def _safe_name(filename):
    base = os.path.basename(filename)
    return re.sub(r"[^\w.\-]+", "_", base) or "clip.mp4"


def download(job_id, item, path):
    with open(path, "wb") as f:
        for part in range(int(item["parts"])):
            r = _request("GET", "nics-video-worker-file", headers=_headers(),
                         params={"job": job_id, "file": item["index"], "part": part}, timeout=(30, 600))
            f.write(r.content)


def upload(job_id, path):
    name = os.path.basename(path)
    size = os.path.getsize(path)
    parts = max(1, -(-size // PART_SIZE))
    with open(path, "rb") as f:
        for part in range(parts):
            _request("POST", "nics-video-worker-upload", data=f.read(PART_SIZE),
                     headers=_headers(**{"Content-Type": "application/octet-stream"}),
                     params={"job": job_id, "name": name, "part": part}, timeout=(30, 600))
    return {"name": name, "size": size, "parts": parts}


def handle(job):
    job_id = str(job["id"])
    job_dir = os.path.join(WORK_DIR, re.sub(r"[^\w\-]", "_", job_id))
    input_dir = os.path.join(job_dir, "input")
    output_dir = os.path.join(job_dir, "output")
    os.makedirs(input_dir, exist_ok=True)
    try:
        call("progress", job_id=job_id, stage="download")
        for item in job.get("inputs", []):
            name = f'{int(item["index"]):03d}_{_safe_name(item["filename"])}'
            if os.path.splitext(name)[1].lower() not in SUPPORTED_EXTENSIONS:
                continue
            download(job_id, item, os.path.join(input_dir, name))

        files = pipeline.run_job(
            input_dir, output_dir, _safe_name(job.get("name") or "nics_video").rsplit(".", 1)[0],
            title=job.get("title"), title_en=job.get("title_en"),
            long_duration=float(job.get("long_duration") or 90),
            short_duration=float(job.get("short_duration") or 30),
            progress=lambda stage: call("progress", job_id=job_id, stage=stage),
        )

        call("progress", job_id=job_id, stage="upload")
        uploaded = [upload(job_id, path) for path in files]
        call("complete", job_id=job_id, files=uploaded)
        print(f"Job {job_id} done: {[u['name'] for u in uploaded]}", flush=True)
    except Exception as e:
        traceback.print_exc()
        try:
            call("fail", job_id=job_id, error=str(e)[-1500:])
        except Exception:
            traceback.print_exc()
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    args = p.parse_args()
    if not TOKEN:
        sys.exit("Set NICS_VIDEO_WORKER_TOKEN (see README, section 10).")

    print(f"NICS Video worker polling {API_BASE} every {POLL_SECONDS:.0f}s", flush=True)
    while True:
        try:
            job = call("claim").get("job")
        except Exception as e:
            print(f"claim failed: {e}", flush=True)
            job = None
        if job:
            handle(job)
        if args.once:
            return
        if not job:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
