"""Per-source analysis: technical probing, scene detection (heuristic),
technical quality + motion (heuristic), CLIP zero-shot tags + prompt
similarity (model-based, zero-shot — not full scene understanding).
Results are cached in analysis/<name>__<hash>.json keyed by file
size+mtime, so unchanged sources are not re-analyzed on the next run."""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import ffutil
import quality
import semantic
from config import INPUT_DIR, ANALYSIS_DIR, SUPPORTED_EXTENSIONS

MIN_CLIP_LEN = 1.2
MAX_CLIP_LEN = 6.0
SCENE_THRESHOLD = 27.0


def _quick_hash(path):
    st = os.stat(path)
    key = f"{path}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _cache_path(path):
    base = os.path.splitext(os.path.basename(path))[0]
    return os.path.join(ANALYSIS_DIR, f"{base}__{_quick_hash(path)}.json")


def detect_scenes(path, duration):
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector

    try:
        video = open_video(path)
        sm = SceneManager()
        sm.add_detector(ContentDetector(threshold=SCENE_THRESHOLD))
        sm.detect_scenes(video)
        scene_list = sm.get_scene_list()
    except Exception as exc:
        return [(0.0, duration)], str(exc)

    if not scene_list:
        return [(0.0, duration)], None

    return [(s.get_seconds(), e.get_seconds()) for s, e in scene_list], None


def split_into_clips(scenes, duration):
    clips = []
    for start, end in scenes:
        seg_len = end - start
        if seg_len <= 0:
            continue
        if seg_len <= MAX_CLIP_LEN:
            if seg_len >= MIN_CLIP_LEN:
                clips.append((start, end))
            continue
        n_parts = max(1, round(seg_len / (MAX_CLIP_LEN * 0.75)))
        part_len = seg_len / n_parts
        for i in range(n_parts):
            s = start + i * part_len
            e = min(start + (i + 1) * part_len, end)
            if e - s >= MIN_CLIP_LEN:
                clips.append((s, e))
    return clips


def analyze_video(path, prompt_text=None, use_clip=True, use_whisper=False, force=False):
    cache_file = _cache_path(path)
    if not force and os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    info = ffutil.video_info(path)
    duration = info["duration"]

    scenes, scene_warning = detect_scenes(path, duration)
    candidate_ranges = split_into_clips(scenes, duration)

    clips = []
    for start, end in candidate_ranges:
        q = quality.analyze_segment_quality(path, start, end)
        mid_frame = q.pop("mid_frame")

        clip_entry = {
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(end - start, 2),
            "technical_quality": q["technical_quality"],
            "sharpness": q["sharpness"],
            "exposure_mean": q["exposure_mean"],
            "exposure_bad": q["exposure_bad"],
            "motion": q["motion"],
            "black_or_static": q["black_or_static"],
            "crop_center": q["crop_center"],
            "clip_tags": [],
            "prompt_similarity": None,
            "warnings": [],
        }
        if q["black_or_static"]:
            clip_entry["warnings"].append("low-motion or near-black segment")
        if q["exposure_bad"]:
            clip_entry["warnings"].append("poor exposure (too dark or too bright)")

        if use_clip and mid_frame is not None:
            try:
                clip_entry["clip_tags"] = semantic.tag_frame(mid_frame)
                if prompt_text:
                    clip_entry["prompt_similarity"] = semantic.prompt_similarity(mid_frame, prompt_text)
            except Exception as exc:
                clip_entry["warnings"].append(f"CLIP tagging failed: {exc}")

        clips.append(clip_entry)

    transcript = None
    if use_whisper and info["has_audio"]:
        try:
            import transcribe
            transcript = transcribe.transcribe(path)
        except Exception as exc:
            transcript = {"error": str(exc)}

    result = {
        "file": path,
        "info": info,
        "scene_warning": scene_warning,
        "clips": clips,
        "transcript": transcript,
        "limitations": [
            "Scene cuts and motion are detected via pixel-level heuristics, not scene understanding.",
            "clip_tags come from CLIP zero-shot matching against a fixed English tag vocabulary — "
            "this is approximate content hinting, not full scene captioning.",
            "prompt_similarity is weaker for non-English prompts, since CLIP's text tower is English-trained.",
        ],
    }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def analyze_folder(input_dir=INPUT_DIR, prompt_text=None, use_clip=True, use_whisper=False, force=False):
    results = {}
    for root, _, files in os.walk(input_dir):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            path = os.path.join(root, name)
            print(f"Analyzing: {path}")
            try:
                results[path] = analyze_video(
                    path, prompt_text=prompt_text, use_clip=use_clip,
                    use_whisper=use_whisper, force=force,
                )
            except Exception as exc:
                results[path] = {"error": str(exc)}
                print(f"  FAILED: {exc}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=INPUT_DIR)
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--no-clip", action="store_true")
    parser.add_argument("--whisper", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out = analyze_folder(
        args.input, prompt_text=args.prompt, use_clip=not args.no_clip,
        use_whisper=args.whisper, force=args.force,
    )
    n_clips = sum(len(v.get("clips", [])) for v in out.values() if "clips" in v)
    print(f"\nDone. {len(out)} files, {n_clips} candidate clips.")
