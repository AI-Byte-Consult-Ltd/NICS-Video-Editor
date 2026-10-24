"""Turns analyzed clips + a text prompt + a style preset into a concrete,
inspectable edit plan (JSON). Selection scoring combines heuristic technical
quality/motion (objective) with CLIP tag/prompt similarity (approximate
semantic signal) — this module does not understand narrative, it ranks and
sequences by those signals and a few hand-written director rules (strong
opening, alternate sources, deliberate ending, limited transition variety)."""
import json
import os
import time

import caption_llm
from config import JOBS_DIR, PRESETS_DIR

FORMAT_DIMS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

XFADE_POOL = [
    "fade", "wipeleft", "wiperight", "slideup", "slidedown",
    "circleopen", "circleclose", "dissolve", "smoothleft", "smoothright",
    "distance", "pixelize",
]

KENBURNS_MOTION_THRESHOLD = 12.0


def load_beats(music_file):
    """Returns sorted beat timestamps (seconds) for the given audio file, or
    None if beat detection isn't possible (missing file, decode failure).
    Honest limitation: librosa's beat tracker is a heuristic and can miss or
    double time on unusual rhythms — cuts fall back to range-based lengths
    whenever no beat lines up within the allowed clip-length window."""
    if not music_file or not os.path.exists(music_file):
        return None
    try:
        import librosa
        y, sr = librosa.load(music_file, sr=None, mono=True)
        _tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        return sorted(float(t) for t in beat_times)
    except Exception:
        return None


def load_presets():
    with open(os.path.join(PRESETS_DIR, "styles.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def _tag_relevance(clip):
    if clip.get("prompt_similarity") is not None:
        return max(0.0, clip["prompt_similarity"])
    tags = clip.get("clip_tags") or []
    if tags:
        return sum(t["similarity"] for t in tags) / len(tags)
    return 0.25


def _orientation_match(src_orientation, target_format):
    target_orientation = "vertical" if target_format == "9:16" else (
        "horizontal" if target_format == "16:9" else "square")
    return 1.0 if src_orientation == target_orientation else 0.6


def score_clip(clip, source_info, target_format):
    technical = clip["technical_quality"]
    motion = min(clip["motion"] / 30.0, 1.0)
    relevance = _tag_relevance(clip)
    orient = _orientation_match(source_info["orientation"], target_format)
    return 0.35 * technical + 0.25 * motion + 0.25 * relevance + 0.15 * orient


def _flatten_pool(analysis_results, target_format):
    pool = []
    for path, result in analysis_results.items():
        if "error" in result or "clips" not in result:
            continue
        for idx, clip in enumerate(result["clips"]):
            if clip["black_or_static"]:
                continue
            entry = dict(clip)
            entry["source"] = path
            entry["source_orientation"] = result["info"]["orientation"]
            entry["score"] = score_clip(clip, result["info"], target_format)
            entry["transcript_text"] = _nearest_transcript(result.get("transcript"), clip["start"], clip["end"])
            entry["crop_center"] = clip.get("crop_center", {"x": 0.5, "y": 0.5})
            pool.append(entry)
    return pool


def _nearest_transcript(transcript, start, end):
    if not transcript or "segments" not in transcript:
        return None
    texts = [s["text"] for s in transcript["segments"] if s["start"] < end and s["end"] > start]
    return " ".join(texts).strip() or None


def _beat_aligned_length(beat_times, current_total, lo, hi, max_available):
    target_end = current_total + ((lo + hi) / 2)
    candidates = [t - current_total for t in beat_times
                  if lo <= (t - current_total) <= min(hi, max_available)]
    if not candidates:
        return None
    return min(candidates, key=lambda length: abs((current_total + length) - target_end))


def _pick_sequence(pool, clip_len_range, target_duration, beat_times=None):
    if not pool:
        return []

    # Group clips by source file, best-first within each source. Selection
    # below round-robins across sources (one clip per source per lap) instead
    # of sorting the whole pool by score and picking greedily — a pure
    # score-sort tends to let a handful of strong source files eat the whole
    # runtime while the rest of a 50+ file folder contributes nothing. The
    # user explicitly asked that every source file get a chance to appear.
    by_source = {}
    for c in pool:
        by_source.setdefault(c["source"], []).append(c)
    for clips in by_source.values():
        clips.sort(key=lambda c: -c["score"])
    source_order = sorted(by_source.keys(), key=lambda s: -by_source[s][0]["score"])

    chosen = []
    used_spans = set()
    total = 0.0
    last_source = None

    def trim(clip):
        lo, hi = clip_len_range
        full = clip["duration"]
        if beat_times:
            aligned = _beat_aligned_length(beat_times, total, lo, hi, full)
            if aligned is not None:
                return aligned
        return min(max(lo, min(hi, full)), full)

    global_best = max(pool, key=lambda c: c["score"])
    opening_len = min(trim(global_best), 2.5)
    chosen.append((global_best, opening_len, "intro"))
    used_spans.add((global_best["source"], global_best["start"]))
    total += opening_len
    last_source = global_best["source"]

    ptr = {src: 0 for src in by_source}
    lst = by_source[global_best["source"]]
    ptr[global_best["source"]] = next(
        (i + 1 for i, c in enumerate(lst) if c is global_best), ptr[global_best["source"]]
    )

    while total < target_duration * 0.92:
        progressed = False
        for src in source_order:
            if src == last_source and len(source_order) > 1:
                continue
            clips = by_source[src]
            p = ptr[src]
            while p < len(clips) and (clips[p]["source"], clips[p]["start"]) in used_spans:
                p += 1
            ptr[src] = p
            if p >= len(clips):
                continue
            clip = clips[p]
            ptr[src] = p + 1
            length = trim(clip)
            if total + length > target_duration * 1.05:
                length = max(clip_len_range[0], target_duration - total)
                if length <= 0.3:
                    continue
            chosen.append((clip, length, "mid"))
            used_spans.add((clip["source"], clip["start"]))
            total += length
            last_source = src
            progressed = True
            if total >= target_duration * 0.92:
                break
        if not progressed:
            break

    remaining = [c for c in pool if (c["source"], c["start"]) not in used_spans]
    closing = max(remaining, key=lambda c: c["score"]) if remaining else None

    if closing and len(chosen) > 1:
        length = min(trim(closing), 3.0)
        chosen.append((closing, length, "outro"))
        total += length
    elif chosen:
        role_fix = chosen[-1]
        chosen[-1] = (role_fix[0], role_fix[1], "outro")

    return chosen


def _wrap_role(i, n):
    if i == 0:
        return "intro"
    if i == n - 1:
        return "outro"
    return "mid"


def build_plan(analysis_results, prompt_text, style, target_duration, target_format, job_id=None,
               music_file=None, burn_captions=True):
    presets = load_presets()
    preset = presets.get(style, presets["default"])
    job_id = job_id or time.strftime("job_%Y%m%d_%H%M%S")

    beat_times = load_beats(music_file)

    pool = _flatten_pool(analysis_results, target_format)
    sequence = _pick_sequence(pool, preset["clip_len_range"], target_duration, beat_times=beat_times)

    timeline = []
    t_cursor = 0.0
    sources_used = set()
    warnings = []
    xfade_idx = 0

    for i, (clip, length, _role) in enumerate(sequence):
        role = _wrap_role(i, len(sequence))
        sources_used.add(clip["source"])
        # Clean hard cuts only (National Geographic-style) — no xfade/wipe
        # transitions. XFADE_POOL is kept defined for possible future use,
        # just not selected here.
        transition = "none" if i == 0 else "cut"

        facts = {
            "tags": [t["tag"] for t in (clip.get("clip_tags") or [])],
            "transcript": clip.get("transcript_text"),
            "style": style,
            "role": role,
        }
        caption = {}
        if burn_captions:
            caption_lang = "ru" if i % 2 == 0 else "en"
            caption = caption_llm.generate_caption(facts, role=role, language=caption_lang)

        entry = {
            "index": i,
            "source": clip["source"],
            "start": clip["start"],
            "end": round(clip["start"] + length, 2),
            "duration": round(length, 2),
            "timeline_start": round(t_cursor, 2),
            "timeline_end": round(t_cursor + length, 2),
            "role": role,
            "transition_in": transition,
            "score": round(clip["score"], 3),
            "reason": _reason_text(clip, role),
            "caption": caption,
            "crop_center": clip.get("crop_center", {"x": 0.5, "y": 0.5}),
            "kenburns": clip["motion"] < KENBURNS_MOTION_THRESHOLD,
            "warnings": clip.get("warnings", []),
        }
        timeline.append(entry)
        t_cursor += length

    if not timeline:
        warnings.append("No usable clips found — all candidates were black/static or failed analysis.")

    if music_file and beat_times is None:
        warnings.append("Beat detection failed or music file unreadable — cuts use range-based lengths, not beat-aligned.")

    total_duration = round(t_cursor, 2)
    if total_duration < target_duration * 0.8:
        warnings.append(
            f"Could only assemble {total_duration}s of usable footage toward a {target_duration}s target; "
            "source material was too limited (duplicates/low quality excluded)."
        )

    plan = {
        "job_id": job_id,
        "prompt": prompt_text,
        "style": style,
        "target_duration": target_duration,
        "actual_duration": total_duration,
        "format": target_format,
        "resolution": FORMAT_DIMS.get(target_format, FORMAT_DIMS["9:16"]),
        "sources_used": sorted(sources_used),
        "timeline": timeline,
        "audio": {
            "music_file": music_file,
            "music_db": preset["music_db"],
            "original_audio_db": preset["orig_audio_db"],
            "mode": "music_plus_original",
            "beat_synced": beat_times is not None,
        },
        "models_used": ["CLIP ViT-B-32 (openai, zero-shot tagging)", "Qwen2.5-1.5B-Instruct (caption phrasing)",
                         "faster-whisper small (only if transcript requested)",
                         "librosa beat tracking (only if music provided)"],
        "warnings": warnings,
        "limitations": [
            "Clip selection quality depends on fixed-vocabulary CLIP tags, not full scene understanding.",
            "Captions are LLM-phrased but grounded only in detected tags/transcript; thin facts produce generic text.",
            "Beat detection (librosa) is heuristic and can mistrack tempo on unusual rhythms.",
            "Smart crop only detects frontal faces (OpenCV Haar cascade) — falls back to center crop otherwise.",
        ],
    }

    os.makedirs(JOBS_DIR, exist_ok=True)
    plan_path = os.path.join(JOBS_DIR, f"{job_id}_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    return plan, plan_path


def _reason_text(clip, role):
    bits = []
    if role == "intro":
        bits.append("strong opening candidate (highest composite score)")
    elif role == "outro":
        bits.append("reserved for a deliberate ending")
    if clip["motion"] > 15:
        bits.append("high motion/dynamic")
    if clip.get("prompt_similarity") and clip["prompt_similarity"] > 0.22:
        bits.append("matches prompt theme")
    tags = clip.get("clip_tags") or []
    if tags:
        bits.append(f"tagged: {tags[0]['tag']}")
    return "; ".join(bits) if bits else "selected by composite quality score"
