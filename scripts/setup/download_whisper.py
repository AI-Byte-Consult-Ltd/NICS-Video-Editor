"""Download faster-whisper 'small' multilingual model into the local project model cache."""
import os

MODELS_DIR = r"D:\NICS-VIDEO\models\whisper"
os.makedirs(MODELS_DIR, exist_ok=True)
os.environ["HF_HOME"] = r"D:\NICS-VIDEO\models\hf_cache"

from faster_whisper import WhisperModel

print("Downloading faster-whisper 'small' model...")
model = WhisperModel("small", device="cpu", compute_type="int8", download_root=MODELS_DIR)
print("Whisper model ready. Cache dir:", MODELS_DIR)
