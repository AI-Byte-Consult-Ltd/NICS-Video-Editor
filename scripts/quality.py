"""Pure heuristics: no model involved. Honest limitation: this measures
sharpness/exposure/motion, not whether a shot is narratively interesting."""
import cv2
import numpy as np

_face_cascade = None
_face_cascade_failed = False


def _load_face_cascade():
    global _face_cascade, _face_cascade_failed
    if _face_cascade is not None or _face_cascade_failed:
        return _face_cascade
    try:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _face_cascade = cv2.CascadeClassifier(path)
    except Exception:
        _face_cascade_failed = True
        _face_cascade = None
    return _face_cascade


def detect_subject_center(frame, default=(0.5, 0.5)):
    """Face-based crop bias, honest limitation: only detects frontal faces
    (Haar cascade), not people/objects in general — falls back to frame
    center when nothing is detected, and MUST NEVER raise: a missing/broken
    cv2 face API (seen with some opencv-python builds) silently disables this
    feature rather than failing the whole clip's analysis."""
    if frame is None:
        return default
    try:
        cascade = _load_face_cascade()
        if cascade is None:
            return default
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        if len(faces) == 0:
            return default
        fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        h, w = frame.shape[:2]
        cx = (fx + fw / 2) / w
        cy = (fy + fh / 2) / h
        return round(min(max(cx, 0.15), 0.85), 3), round(min(max(cy, 0.15), 0.85), 3)
    except Exception:
        return default


def sample_frames(path, times):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = []
    for t in times:
        frame_idx = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        frames.append(frame if ok else None)
    cap.release()
    return frames


def sharpness_score(frame):
    if frame is None:
        return 0.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def exposure_score(frame):
    if frame is None:
        return 0.0, True
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    bad = mean < 25 or mean > 230
    return mean, bad


def motion_score(frame_a, frame_b):
    if frame_a is None or frame_b is None:
        return 0.0
    a = cv2.cvtColor(cv2.resize(frame_a, (160, 90)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(cv2.resize(frame_b, (160, 90)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.mean(np.abs(a - b)))


def is_black_or_static(frames):
    valid = [f for f in frames if f is not None]
    if not valid:
        return True
    means = [exposure_score(f)[0] for f in valid]
    return max(means) < 8


def analyze_segment_quality(path, start, end, n_samples=4):
    times = [start + (end - start) * i / max(n_samples - 1, 1) for i in range(n_samples)]
    frames = sample_frames(path, times)

    sharpness_vals = [sharpness_score(f) for f in frames if f is not None]
    exposures = [exposure_score(f) for f in frames if f is not None]
    motions = [motion_score(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]

    avg_sharpness = float(np.mean(sharpness_vals)) if sharpness_vals else 0.0
    avg_exposure = float(np.mean([e[0] for e in exposures])) if exposures else 0.0
    exposure_bad = any(e[1] for e in exposures)
    avg_motion = float(np.mean(motions)) if motions else 0.0
    black_or_static = is_black_or_static(frames)

    technical_quality = max(0.0, min(1.0, (
        0.5 * min(avg_sharpness / 400.0, 1.0) +
        0.3 * (0.0 if exposure_bad else 1.0) +
        0.2 * (0.0 if black_or_static else 1.0)
    )))

    mid_frame = frames[len(frames) // 2]
    crop_cx, crop_cy = detect_subject_center(mid_frame)

    return {
        "sharpness": round(avg_sharpness, 1),
        "exposure_mean": round(avg_exposure, 1),
        "exposure_bad": exposure_bad,
        "motion": round(avg_motion, 2),
        "black_or_static": black_or_static,
        "technical_quality": round(technical_quality, 3),
        "crop_center": {"x": crop_cx, "y": crop_cy},
        "mid_frame": mid_frame,
    }
