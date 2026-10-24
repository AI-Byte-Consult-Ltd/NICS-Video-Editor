"""Speech-to-text via faster-whisper. Honest limitation: works only on audible,
reasonably clear speech; music/noise/silence yields no transcript, and no
transcript means captions fall back to tag-based neutral text, never invented
dialogue."""
from faster_whisper import WhisperModel

from config import WHISPER_MODEL_DIR

_model = None


def _load():
    global _model
    if _model is None:
        _model = WhisperModel("small", device="cpu", compute_type="int8", download_root=WHISPER_MODEL_DIR)
    return _model


def transcribe(path):
    model = _load()
    segments, info = model.transcribe(path, beam_size=1, vad_filter=True)
    result = []
    for seg in segments:
        result.append({
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
        })
    return {"language": info.language, "segments": result}
