"""Standalone CLI for generating a cover image from an existing plan.
Usage: python make_cover.py --plan jobs/xxx_plan.json --title "..." [--kicker "..."] [--bg-index 0] [--output path.png]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import render as render_mod

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--subtitle", default=None)
    p.add_argument("--kicker", default=None)
    p.add_argument("--bg-index", type=int, default=0)
    p.add_argument("--output", default=None)
    args = p.parse_args()

    with open(args.plan, "r", encoding="utf-8") as f:
        plan = json.load(f)

    path = render_mod.generate_title_image(
        plan, args.title, title_subtitle=args.subtitle, kicker=args.kicker,
        output_path=args.output, bg_clip_index=args.bg_index,
    )
    print(path)
