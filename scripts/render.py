"""Builds and runs the ffmpeg filter graph for a given plan JSON. Hard cuts
use a concat chain; 'fade' transitions use a pairwise xfade chain. Original
per-clip audio is concatenated into a bed (no crossfade on audio — a known,
documented simplification) and mixed with the music track per the plan's
audio settings. Captions are burned with drawtext, timed to the plan's
absolute timeline, inside a safe vertical zone."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import (FFMPEG, OUTPUT_DIR, LOGS_DIR, CAPTION_FONT, CAPTION_FONT_PLAIN, TITLE_FONT_PLAIN,
                    KICKER_FONT_PLAIN, ff_font_path, today_output_dir)
import subprocess
from PIL import Image, ImageDraw, ImageFont

_font_cache = {}


def _get_font(fontsize, font_path=None):
    font_path = font_path or CAPTION_FONT_PLAIN
    key = (font_path, fontsize)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(font_path, fontsize)
    return _font_cache[key]

TRANSITION_DURATION = 0.35

# Poster-style cover design (approved by the user: Disney+ card lettering —
# bold color fill with a double outline, plus a small script-font "studio"
# wordmark). Font paths need two forms: colon-escaped for ffmpeg drawtext
# filter strings, plain for PIL (used only to measure text width for wrap).
TITLE_FONT_FF = ff_font_path(TITLE_FONT_PLAIN)
KICKER_FONT_FF = ff_font_path(KICKER_FONT_PLAIN)
TITLE_FILL_COLOR = "#FFD400"
TITLE_OUTLINE_COLOR = "#D1282D"


def _escape_drawtext(text):
    text = text.replace("\\", "\\\\\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "’")
    text = text.replace("%", "\\%")
    return text


def _safe_wrap(text, frame_width, fontsize, max_lines=3, safe_margin=0.9, font_path=None):
    font = _get_font(fontsize, font_path)
    max_width = frame_width * safe_margin

    def width_of(s):
        return font.getlength(s)

    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and width_of(trial) > max_width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)

    final_lines = []
    for line in lines:
        if width_of(line) <= max_width:
            final_lines.append(line)
            continue
        buf = ""
        for ch in line:
            trial = buf + ch
            if buf and width_of(trial) > max_width:
                final_lines.append(buf)
                buf = ch
            else:
                buf = trial
        if buf:
            final_lines.append(buf)

    return final_lines[:max_lines]


def _build_video_chain(labels, durations, transitions):
    ops = []
    running = labels[0]
    running_dur = durations[0]
    for i in range(1, len(labels)):
        trans_name = transitions[i]
        td = TRANSITION_DURATION if trans_name != "cut" else 0.0
        out_label = f"vrun{i}"
        if td > 0 and running_dur > td:
            offset = round(running_dur - td, 3)
            ops.append(
                f"[{running}][{labels[i]}]xfade=transition={trans_name}:duration={td}:offset={offset}[{out_label}]"
            )
            running_dur = running_dur + durations[i] - td
        else:
            ops.append(f"[{running}][{labels[i]}]concat=n=2:v=1:a=0[{out_label}]")
            running_dur = running_dur + durations[i]
        tb_label = f"{out_label}tb"
        ops.append(f"[{out_label}]settb=1/30,fps=30[{tb_label}]")
        running = tb_label
    return ops, running, running_dur


def _build_audio_chain(labels):
    if len(labels) == 1:
        return [], labels[0]
    ops = []
    running = labels[0]
    for i in range(1, len(labels)):
        out_label = f"arun{i}"
        ops.append(f"[{running}][{labels[i]}]concat=n=2:v=0:a=1[{out_label}]")
        running = out_label
    return ops, running


def _draw_title_card(filter_parts, video_label, width, height, text, subtitle=None, duration=2.5):
    fade_expr = f"if(lt(t,0.5),t/0.5,if(lt(t,{duration}-0.5),1,if(lt(t,{duration}),({duration}-t)/0.5,0)))"

    title_fontsize = round(height * 0.052)
    title_lines = _safe_wrap(text, width, title_fontsize, max_lines=4, safe_margin=0.85)
    title_line_height = round(title_fontsize * 1.2)
    title_block_h = len(title_lines) * title_line_height
    base_y = round(height * 0.44 - title_block_h / 2)

    for li, line in enumerate(title_lines):
        label = f"titlecard{li}"
        line_esc = _escape_drawtext(line)
        y = base_y + li * title_line_height
        filter_parts.append(
            f"[{video_label}]drawtext=fontfile='{CAPTION_FONT}':text='{line_esc}':"
            f"fontsize={title_fontsize}:fontcolor=white:borderw=4:bordercolor=black@0.6:"
            f"x=(w-text_w)/2:y={y}:alpha='{fade_expr}':enable='between(t,0,{duration})'[{label}]"
        )
        video_label = label

    if subtitle:
        sub_fontsize = round(height * 0.03)
        sub_lines = _safe_wrap(subtitle, width, sub_fontsize, max_lines=1, safe_margin=0.85)
        for li, line in enumerate(sub_lines):
            label = f"titlesub{li}"
            line_esc = _escape_drawtext(line)
            y = base_y + title_block_h + round(title_fontsize * 0.25) + li * round(sub_fontsize * 1.2)
            filter_parts.append(
                f"[{video_label}]drawtext=fontfile='{CAPTION_FONT}':text='{line_esc}':"
                f"fontsize={sub_fontsize}:fontcolor=white@0.9:borderw=2:bordercolor=black@0.5:"
                f"x=(w-text_w)/2:y={y}:alpha='{fade_expr}':enable='between(t,0,{duration})'[{label}]"
            )
            video_label = label

    return video_label


def _make_bottom_gradient_png(width, height, path, start_frac=0.40, max_alpha=200, power=1.3):
    """Soft black gradient, transparent at top fading to max_alpha at the
    bottom — lets the cover photo show through fully while keeping the
    poster text readable. Not a box/frame: no hard edge, just a fade."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    start_y = int(height * start_frac)
    span = max(height - start_y, 1)
    for y in range(start_y, height):
        t = (y - start_y) / span
        alpha = int(min(t * 1.3, 1.0) ** power * max_alpha)
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    img.save(path)


def generate_title_image(plan, title_text, title_subtitle=None, output_path=None, kicker=None, bg_clip_index=0):
    """Renders a standalone cover image in the approved poster style: bottom
    gradient for legibility, title text lower-left with a yellow-fill /
    red-outline / white-ring treatment (Disney+ card lettering look), and a
    small script-font studio wordmark above it. No subtitle is shown unless
    explicitly passed — years/dates are intentionally left off by default."""
    width, height = plan["resolution"]
    first_clip = plan["timeline"][bg_clip_index]
    is_vertical = height > width
    kicker_text = kicker or "Nics Studio"

    left_x = round(width * 0.06)
    title_fontsize = round(height * (0.062 if is_vertical else 0.108))
    title_line_h = round(title_fontsize * 1.05)
    kicker_fontsize = round(height * 0.034)
    sub_fontsize = round(height * 0.03)
    # Vertical covers sit higher still: TikTok's own UI (view-count badge on
    # thumbnails, caption/username/nav once playing) eats the bottom third,
    # and 0.30 wasn't enough clearance — bumped to 0.34 (+4% of height).
    bottom_margin = round(height * (0.34 if is_vertical else 0.08))

    title_lines = _safe_wrap(title_text, width, title_fontsize, max_lines=4, safe_margin=0.88,
                              font_path=TITLE_FONT_PLAIN)
    sub_lines = _safe_wrap(title_subtitle, width, sub_fontsize, max_lines=1, safe_margin=0.88,
                            font_path=TITLE_FONT_PLAIN) if title_subtitle else []

    # Title sits at the same standard baseline on every cover, with or
    # without a subtitle — a subtitle is added BELOW it, never pushes the
    # title itself up, so "USA"/"JAPAN"/etc. all line up across covers.
    last_line_y = height - bottom_margin - title_line_h
    line_ys = [last_line_y - (len(title_lines) - 1 - i) * title_line_h for i in range(len(title_lines))]
    kicker_y = line_ys[0] - round(kicker_fontsize * 1.5)

    grad_path = os.path.join(LOGS_DIR, f"{plan['job_id']}_grad.png")
    _make_bottom_gradient_png(width, height, grad_path)

    filter_parts = [
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1[bg0]",
        f"[1:v]format=rgba[grad0]",
        f"[bg0][grad0]overlay=0:0[bg]",
    ]
    video_label = "bg"

    kicker_esc = _escape_drawtext(kicker_text)
    filter_parts.append(
        f"[{video_label}]drawtext=fontfile='{KICKER_FONT_FF}':text='{kicker_esc}':"
        f"fontsize={kicker_fontsize}:fontcolor=white:borderw=2:bordercolor=black@0.5:"
        f"x={left_x}:y={kicker_y}[kicker]"
    )
    video_label = "kicker"

    for li, line in enumerate(title_lines):
        line_esc = _escape_drawtext(line)
        y = line_ys[li]
        lab1, lab2, lab3 = f"t{li}o1", f"t{li}o2", f"t{li}o3"
        filter_parts.append(
            f"[{video_label}]drawtext=fontfile='{TITLE_FONT_FF}':text='{line_esc}':"
            f"fontsize={title_fontsize}:fontcolor={TITLE_OUTLINE_COLOR}:borderw=13:"
            f"bordercolor={TITLE_OUTLINE_COLOR}:x={left_x}:y={y}[{lab1}]"
        )
        filter_parts.append(
            f"[{lab1}]drawtext=fontfile='{TITLE_FONT_FF}':text='{line_esc}':"
            f"fontsize={title_fontsize}:fontcolor=white:borderw=7:bordercolor=white:"
            f"x={left_x}:y={y}[{lab2}]"
        )
        filter_parts.append(
            f"[{lab2}]drawtext=fontfile='{TITLE_FONT_FF}':text='{line_esc}':"
            f"fontsize={title_fontsize}:fontcolor={TITLE_FILL_COLOR}:borderw=2:"
            f"bordercolor=black@0.35:x={left_x}:y={y}[{lab3}]"
        )
        video_label = lab3

    if sub_lines:
        sub_y = line_ys[-1] + title_line_h + round(sub_fontsize * 0.4)
        line_esc = _escape_drawtext(sub_lines[0])
        filter_parts.append(
            f"[{video_label}]drawtext=fontfile='{CAPTION_FONT}':text='{line_esc}':"
            f"fontsize={sub_fontsize}:fontcolor=white:borderw=2:bordercolor=black@0.5:"
            f"x={left_x}:y={sub_y}[titlesub]"
        )
        video_label = "titlesub"

    output_path = output_path or os.path.join(today_output_dir(), f"{plan['job_id']}_title.png")
    args = [
        "-ss", f"{first_clip['start']:.3f}", "-i", first_clip["source"],
        "-i", grad_path,
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{video_label}]", "-frames:v", "1", output_path,
    ]
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Title image generation failed: {result.stderr[-1500:]}")
    return output_path


def _escape_filter_path(path):
    return path.replace("\\", "/").replace(":", "\\:")


def _stabilize_pass(clip, idx, job_id):
    """Runs vidstabdetect on a single trimmed clip, returns the .trf path, or
    None if the detect pass fails (stabilization is then silently skipped for
    that clip — never blocks the render)."""
    tmp_dir = os.path.join(LOGS_DIR, "vidstab_tmp", job_id)
    os.makedirs(tmp_dir, exist_ok=True)
    trf_path = os.path.join(tmp_dir, f"clip{idx}.trf")
    args = [
        "-ss", f"{clip['start']:.3f}", "-t", f"{clip['duration']:.3f}", "-i", clip["source"],
        "-vf", f"vidstabdetect=shakiness=8:accuracy=15:result='{_escape_filter_path(trf_path)}'",
        "-f", "null", "-",
    ]
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if result.returncode != 0 or not os.path.exists(trf_path):
        return None
    return trf_path


COLOR_GRADE = "eq=contrast=1.07:saturation=1.14:brightness=0.01,curves=preset=medium_contrast,vignette=PI/5"


def _prepare_music_track(music_file, start, job_id):
    """Trims the track so it starts at `start` seconds in (the hook/drop),
    so that when the render loops it for a long video it loops the hook
    section rather than jumping back to the track's quiet intro."""
    trimmed_path = os.path.join(LOGS_DIR, f"{job_id}_music_trimmed.wav")
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{start:.3f}", "-i", music_file, trimmed_path]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Music trim failed: {result.stderr[-1000:]}")
    return trimmed_path


def render(plan, music_file=None, music_start=0.0, output_path=None, burn_captions=True,
           title_text=None, title_subtitle=None, title_duration=2.5, stabilize=True):
    width, height = plan["resolution"]
    timeline = plan["timeline"]
    if not timeline:
        raise RuntimeError("Plan has an empty timeline — nothing to render.")

    inputs_args = []
    filter_parts = []
    vlabels, alabels, durations = [], [], []

    for i, clip in enumerate(timeline):
        start, dur = clip["start"], clip["duration"]
        inputs_args += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", clip["source"]]
        vlab, alab = f"v{i}in", f"a{i}in"

        pre = ""
        if stabilize:
            trf_path = _stabilize_pass(clip, i, plan["job_id"])
            if trf_path:
                # optzoom=0 (no crop) left visible black borders flickering
                # in and out as the stabilization shift varies frame to
                # frame. optzoom=1 computes ONE static zoom for the whole
                # clip (just enough to cover the border at its worst point) —
                # a small constant crop instead of a flickering border or a
                # continuously creeping dynamic zoom (optzoom=2).
                pre = f"vidstabtransform=input='{_escape_filter_path(trf_path)}':smoothing=15:optzoom=1:interpol=linear,"

        crop_center = clip.get("crop_center") or {"x": 0.5, "y": 0.5}
        cx = min(max(crop_center.get("x", 0.5), 0.15), 0.85)
        cy = min(max(crop_center.get("y", 0.5), 0.15), 0.85)
        crop_expr = f"crop={width}:{height}:x='(iw-{width})*{cx}':y='(ih-{height})*{cy}'"

        # Ken Burns (slow zoom on static clips) is disabled: this ffmpeg build's
        # crop filter has no 'eval' option, so a time-variant crop expression
        # ('t' in w/h) can only be evaluated once at init and fails at runtime.
        kenburns = ""

        filter_parts.append(
            f"[{i}:v]{pre}scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"{crop_expr}{kenburns},{COLOR_GRADE},setsar=1,fps=30,settb=1/30[{vlab}]"
        )
        filter_parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[{alab}]")
        vlabels.append(vlab)
        alabels.append(alab)
        durations.append(dur)

    transitions = [clip["transition_in"] for clip in timeline]
    vops, final_v, total_dur = _build_video_chain(vlabels, durations, transitions)
    filter_parts += vops

    aops, final_a_bed = _build_audio_chain(alabels)
    filter_parts += aops

    audio_cfg = plan.get("audio", {})
    music_db = audio_cfg.get("music_db", -14)
    orig_db = audio_cfg.get("original_audio_db", -22)
    mode = audio_cfg.get("mode", "music_plus_original")

    audio_inputs_extra = []
    final_audio_label = final_a_bed
    if music_file and mode in ("music_plus_original", "music_only"):
        music_input_idx = len(timeline)
        music_src = _prepare_music_track(music_file, music_start, plan["job_id"]) if music_start > 0 else music_file
        audio_inputs_extra += ["-stream_loop", "-1", "-i", music_src]
        filter_parts.append(
            f"[{music_input_idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"atrim=0:{total_dur:.3f},afade=t=in:d=0.6,afade=t=out:st={max(total_dur - 0.8, 0):.3f}:d=0.8,"
            f"volume={music_db}dB[music]"
        )
        if mode == "music_plus_original":
            filter_parts.append(f"[{final_a_bed}]volume={orig_db}dB[origbed]")
            filter_parts.append("[music][origbed]amix=inputs=2:duration=longest:dropout_transition=0[afinal]")
        else:
            filter_parts.append("[music]anull[afinal]")
        final_audio_label = "afinal"
    elif mode == "original_only":
        filter_parts.append(f"[{final_a_bed}]volume={orig_db}dB[afinal]")
        final_audio_label = "afinal"
    else:
        filter_parts.append(f"[{final_a_bed}]anull[afinal]")
        final_audio_label = "afinal"

    video_with_text = final_v
    for i, clip in enumerate(timeline):
        if not burn_captions:
            break
        cap = clip.get("caption") or {}
        text = cap.get("ru") or cap.get("en") or ""
        if not text:
            continue
        fontsize = round(height * 0.036)
        lines = _safe_wrap(text, width, fontsize)
        t0, t1 = clip["timeline_start"], clip["timeline_end"]

        line_height = round(fontsize * 1.2)
        base_y = round(height * 0.73 - (len(lines) - 1) * line_height / 2)
        for li, line in enumerate(lines):
            label = f"txt{i}l{li}"
            line_esc = _escape_drawtext(line)
            y = base_y + li * line_height
            filter_parts.append(
                f"[{video_with_text}]drawtext=fontfile='{CAPTION_FONT}':text='{line_esc}':"
                f"fontsize={fontsize}:fontcolor=white:borderw=3:bordercolor=black@0.7:"
                f"x=(w-text_w)/2:y={y}:enable='between(t,{t0:.2f},{t1:.2f})'[{label}]"
            )
            video_with_text = label

    if title_text:
        video_with_text = _draw_title_card(
            filter_parts, video_with_text, width, height, title_text, title_subtitle, title_duration
        )

    filter_complex = ";".join(filter_parts)

    output_path = output_path or os.path.join(today_output_dir(), f"{plan['job_id']}.mp4")

    def _try_encode(vcodec):
        args = (
            inputs_args + audio_inputs_extra +
            ["-filter_complex", filter_complex,
             "-map", f"[{video_with_text}]", "-map", f"[{final_audio_label}]",
             "-c:v", vcodec, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", output_path]
        )
        cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + args
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800), cmd

    result, cmd = _try_encode("h264_qsv")
    encoder_used = "h264_qsv"
    if result.returncode != 0:
        result, cmd = _try_encode("libx264")
        encoder_used = "libx264 (qsv fallback)"

    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f"{plan['job_id']}_render.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("CMD:\n" + " ".join(cmd) + "\n\nSTDERR:\n" + result.stderr)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg render failed (see {log_path}): {result.stderr[-2000:]}")

    return {
        "output_path": output_path,
        "encoder_used": encoder_used,
        "estimated_duration": round(total_dur, 2),
        "log_path": log_path,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--music", default=None)
    args = parser.parse_args()
    with open(args.plan, "r", encoding="utf-8") as f:
        plan = json.load(f)
    info = render(plan, music_file=args.music)
    print(json.dumps(info, ensure_ascii=False, indent=2))
