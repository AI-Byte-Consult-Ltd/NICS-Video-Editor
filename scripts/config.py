import os

# Runtime (not setup/download scripts) must never touch the network: once
# models are cached locally, force offline mode so a missing/renamed file
# fails loudly instead of silently reaching out to the internet.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WINDOWS = os.name == "nt"

# Data root (input/output/models/cache). Override with NICS_VIDEO_ROOT; the
# default keeps the original workstation layout on Windows.
ROOT = os.environ.get("NICS_VIDEO_ROOT") or (r"D:\NICS-VIDEO" if IS_WINDOWS else os.path.expanduser("~/nics-video"))
INPUT_DIR = os.path.join(ROOT, "input")
OUTPUT_DIR = os.path.join(ROOT, "output")
ASSETS_DIR = os.path.join(ROOT, "assets")
JOBS_DIR = os.path.join(ROOT, "jobs")
ANALYSIS_DIR = os.path.join(ROOT, "analysis")
MODELS_DIR = os.environ.get("NICS_VIDEO_MODELS_DIR") or os.path.join(ROOT, "models")
PRESETS_DIR = os.environ.get("NICS_VIDEO_PRESETS_DIR") or os.path.join(REPO_DIR, "presets")
LOGS_DIR = os.path.join(ROOT, "logs")

CLIP_MODEL_DIR = os.path.join(MODELS_DIR, "clip")
WHISPER_MODEL_DIR = os.path.join(MODELS_DIR, "whisper")
LLM_MODEL_PATH = os.path.join(MODELS_DIR, "llm", "qwen2.5-1.5b-instruct-q4_k_m.gguf")

FFMPEG = os.environ.get("NICS_VIDEO_FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("NICS_VIDEO_FFPROBE", "ffprobe")


def ff_font_path(path):
    """Font path in the colon-escaped form ffmpeg drawtext expects."""
    return path.replace("\\", "/").replace(":", "\\:")


def _font(env_name, windows_name, linux_path):
    if os.environ.get(env_name):
        return os.environ[env_name]
    return f"C:/Windows/Fonts/{windows_name}" if IS_WINDOWS else linux_path


# Plain paths (PIL); ffmpeg drawtext uses ff_font_path(). On Linux the
# Windows fonts are replaced by DejaVu (fonts-dejavu-core) unless overridden.
CAPTION_FONT_PLAIN = _font("NICS_VIDEO_CAPTION_FONT", "arialbd.ttf",
                           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
TITLE_FONT_PLAIN = _font("NICS_VIDEO_TITLE_FONT", "comicbd.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
KICKER_FONT_PLAIN = _font("NICS_VIDEO_KICKER_FONT", "segoescb.ttf",
                          "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf")
CAPTION_FONT = ff_font_path(CAPTION_FONT_PLAIN)

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp"}

for _d in (INPUT_DIR, OUTPUT_DIR, ASSETS_DIR, JOBS_DIR, ANALYSIS_DIR, MODELS_DIR, LOGS_DIR):
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
