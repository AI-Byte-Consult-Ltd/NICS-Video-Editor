"""One full job, as make_video.bat does it, callable from Python: analyze a
folder once, then build and render the horizontal long video and the vertical
short, plus four covers (RU/EN for each). Used by worker.py for site jobs.

Usage:
  python pipeline.py --input path/to/clips --output path/to/out --name trip2 --title "..." [--title-en "..."]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from config import ASSETS_DIR
import analyze
import planner
import render as render_mod

DEFAULT_MUSIC = os.path.join(ASSETS_DIR, "test_music.mp3")

VARIANTS = [
    # (suffix, prompt, style, format, duration key)
    ("long_v1", "Лучшие и самые интересные моменты из видео", "cinematic", "16:9", "long_duration"),
    ("shorts_v1", "Лучшие и самые интересные моменты из видео, энергичный ролик", "dynamic", "9:16", "short_duration"),
]


# Signature on packages made with the free credits ([26 VIDEO] sends
# job.watermark = true for them); paid plans render without it.
WATERMARK_TEXT = "NICS Video · aibyteconsult.com"

def run_job(input_dir, output_dir, name, title=None, title_en=None, long_duration=90.0,
            short_duration=30.0, music=None, progress=None, watermark=False):
    """Returns the list of produced file paths. `progress(stage)` is called
    with one of: analyze, plan, render_long, render_shorts, covers.
    `watermark` adds the small site signature (packages from free credits)."""
    def report(stage):
        if progress:
            progress(stage)

    os.makedirs(output_dir, exist_ok=True)
    if music is None and os.path.exists(DEFAULT_MUSIC):
        music = DEFAULT_MUSIC
    durations = {"long_duration": long_duration, "short_duration": short_duration}

    report("analyze")
    results = analyze.analyze_folder(input_dir, prompt_text=VARIANTS[0][1], use_clip=True)
    usable = {k: v for k, v in results.items() if "clips" in v}
    if not usable:
        raise RuntimeError("No analyzable videos found in the upload.")

    report("plan")
    plans = []
    for suffix, prompt, style, fmt, dur_key in VARIANTS:
        plan, _ = planner.build_plan(
            usable, prompt, style, durations[dur_key], fmt, job_id=f"{name}_{suffix}",
            music_file=music, burn_captions=False,
        )
        plans.append((suffix, plan))

    outputs = []
    for suffix, plan in plans:
        report("render_" + suffix.split("_")[0])
        info = render_mod.render(
            plan, music_file=music, burn_captions=False,
            output_path=os.path.join(output_dir, f"{name}_{suffix}.mp4"),
            watermark_text=WATERMARK_TEXT if watermark else None,
        )
        outputs.append(info["output_path"])

    title = title or title_en
    title_en = title_en or title
    if title:
        report("covers")
        for suffix, plan in plans:
            for text, tail in ((title, "title"), (title_en, "title_en")):
                outputs.append(render_mod.generate_title_image(
                    plan, text, output_path=os.path.join(output_dir, f"{name}_{suffix}_{tail}.png"),
                ))
    return outputs


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--title", default=None)
    p.add_argument("--title-en", default=None)
    p.add_argument("--long-duration", type=float, default=90.0)
    p.add_argument("--short-duration", type=float, default=30.0)
    p.add_argument("--music", default=None)
    a = p.parse_args()
    files = run_job(a.input, a.output, a.name, a.title, a.title_en, a.long_duration,
                    a.short_duration, a.music, progress=lambda s: print(f"[{s}]", flush=True))
    print(json.dumps(files, ensure_ascii=False, indent=2))
