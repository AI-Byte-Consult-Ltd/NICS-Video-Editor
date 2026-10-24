"""Main launcher. Takes a text job (prompt + style + duration + format),
analyzes input/, builds a plan, and either stops for preview or renders.

Usage:
  python run.py --prompt "..." --style dynamic --duration 30 --format 9:16 --mode preview
  python run.py --render-plan jobs/job_xxx_plan.json --music assets/track.mp3
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Windows consoles default stdout/stderr to the system codepage (cp1252),
# which can't encode Cyrillic path segments (e.g. the dated output folder
# name) — reconfigure to utf-8 so printing paths/JSON never crashes.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from config import INPUT_DIR
import analyze
import planner
import render as render_mod


def cmd_edit(args):
    print(f"[1/3] Analyzing sources in {args.input} ...")
    results = analyze.analyze_folder(
        args.input, prompt_text=args.prompt, use_clip=True,
        use_whisper=args.whisper, force=args.force_analysis,
    )
    usable = {k: v for k, v in results.items() if "clips" in v}
    if not usable:
        print("No analyzable videos found. Nothing to do.")
        return

    if args.exclude_from:
        excluded = set()
        for plan_path_ in args.exclude_from:
            with open(plan_path_, "r", encoding="utf-8") as f:
                excluded.update(json.load(f).get("sources_used", []))
        before = len(usable)
        usable = {k: v for k, v in usable.items() if k not in excluded}
        print(f"Excluded {before - len(usable)} source(s) already used in {args.exclude_from}.")

    print(f"[2/3] Building edit plan (style={args.style}, duration={args.duration}s, format={args.format}) ...")
    plan, plan_path = planner.build_plan(
        usable, args.prompt, args.style, args.duration, args.format, job_id=args.job_id,
        music_file=args.music, burn_captions=not args.no_captions,
    )
    print(f"Plan saved: {plan_path}")
    print(f"Actual duration: {plan['actual_duration']}s across {len(plan['sources_used'])} source(s).")
    for w in plan["warnings"]:
        print(f"  WARNING: {w}")

    if args.mode == "preview":
        print("\nPreview mode — review the plan JSON, then render with:")
        print(f'  python run.py --render-plan "{plan_path}"' + (f' --music "{args.music}"' if args.music else ""))
        return

    print("[3/3] Rendering ...")
    info = render_mod.render(
        plan, music_file=args.music, music_start=args.music_start,
        burn_captions=not args.no_captions, stabilize=not args.no_stabilize,
    )
    if args.title:
        info["title_image"] = render_mod.generate_title_image(plan, args.title, args.subtitle)
    print(json.dumps(info, ensure_ascii=False, indent=2))


def cmd_render_plan(args):
    with open(args.render_plan, "r", encoding="utf-8") as f:
        plan = json.load(f)
    if args.job_id:
        plan["job_id"] = args.job_id
    print("[1/1] Rendering from existing plan ...")
    info = render_mod.render(
        plan, music_file=args.music, music_start=args.music_start,
        burn_captions=not args.no_captions, stabilize=not args.no_stabilize,
    )
    if args.title:
        info["title_image"] = render_mod.generate_title_image(plan, args.title, args.subtitle)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", default="")
    p.add_argument("--style", default="default")
    p.add_argument("--duration", type=float, default=30.0)
    p.add_argument("--format", default="9:16", choices=["9:16", "16:9", "1:1"])
    p.add_argument("--input", default=INPUT_DIR)
    p.add_argument("--mode", default="preview", choices=["preview", "auto"])
    p.add_argument("--whisper", action="store_true")
    p.add_argument("--force-analysis", action="store_true")
    p.add_argument("--music", default=None)
    p.add_argument("--music-start", type=float, default=0.0)
    p.add_argument("--job-id", default=None)
    p.add_argument("--render-plan", default=None)
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--title", default=None)
    p.add_argument("--subtitle", default=None)
    p.add_argument("--no-stabilize", action="store_true")
    p.add_argument("--exclude-from", action="append", default=[])
    args = p.parse_args()

    if args.render_plan:
        cmd_render_plan(args)
    else:
        cmd_edit(args)
