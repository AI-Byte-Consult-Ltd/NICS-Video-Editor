import os

# Runtime (not setup/download scripts) must never touch the network: once
# models are cached locally, force offline mode so a missing/renamed file
# fails loudly instead of silently reaching out to the internet.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = r"D:\NICS-VIDEO"
INPUT_DIR = os.path.join(ROOT, "input")
OUTPUT_DIR = os.path.join(ROOT, "output")
ASSETS_DIR = os.path.join(ROOT, "assets")
JOBS_DIR = os.path.join(ROOT, "jobs")
ANALYSIS_DIR = os.path.join(ROOT, "analysis")
MODELS_DIR = os.path.join(ROOT, "models")
PRESETS_DIR = os.path.join(ROOT, "presets")
LOGS_DIR = os.path.join(ROOT, "logs")

CLIP_MODEL_DIR = os.path.join(MODELS_DIR, "clip")
WHISPER_MODEL_DIR = os.path.join(MODELS_DIR, "whisper")
LLM_MODEL_PATH = os.path.join(MODELS_DIR, "llm", "qwen2.5-1.5b-instruct-q4_k_m.gguf")

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

CAPTION_FONT = r"C\:/Windows/Fonts/arialbd.ttf"
CAPTION_FONT_PLAIN = r"C:/Windows/Fonts/arialbd.ttf"

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp"}

for _d in (INPUT_DIR, OUTPUT_DIR, ASSETS_DIR, JOBS_DIR, ANALYSIS_DIR, MODELS_DIR, PRESETS_DIR, LOGS_DIR):
    os.makedirs(_d, exist_ok=True)

_MONTHS_RU_GENITIVE = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


def today_output_dir():
    """Finished videos/covers go into output/<day month>/ (e.g. '15 октября')
    so each day's results land in their own folder automatically."""
    import datetime
    today = datetime.date.today()
    folder = os.path.join(OUTPUT_DIR, f"{today.day} {_MONTHS_RU_GENITIVE[today.month]}")
    os.makedirs(folder, exist_ok=True)
    return folder
