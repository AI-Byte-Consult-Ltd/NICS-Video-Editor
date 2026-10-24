import json
import subprocess

from config import FFPROBE, FFMPEG


def probe(path):
    cmd = [
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def video_info(path):
    data = probe(path)
    fmt = data.get("format", {})
    vstream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    astream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if vstream is None:
        raise RuntimeError(f"No video stream in {path}")

    duration = float(fmt.get("duration") or vstream.get("duration") or 0.0)
    width = int(vstream["width"])
    height = int(vstream["height"])
    rot = 0
    side_data = vstream.get("side_data_list") or []
    for sd in side_data:
        if "rotation" in sd:
            rot = abs(int(sd["rotation"]))
    if rot in (90, 270):
        width, height = height, width

    fr = vstream.get("avg_frame_rate", "0/1")
    try:
        num, den = fr.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 0.0
    except Exception:
        fps = 0.0

    orientation = "vertical" if height > width else ("horizontal" if width > height else "square")

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "has_audio": astream is not None,
        "orientation": orientation,
        "codec": vstream.get("codec_name"),
    }


def run_ffmpeg(args, timeout=1800):
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + args
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return out.returncode, out.stdout, out.stderr
