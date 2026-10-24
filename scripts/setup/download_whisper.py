"""Download faster-whisper 'small' multilingual model into the local project model cache."""
import os
import sys

# Setup scripts are the only ones allowed online; set before config is
# imported, since config defaults the hub to offline mode.
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MODELS_DIR as _ROOT_MODELS

MODELS_DIR = os.path.join(_ROOT_MODELS, "whisper")
os.makedirs(MODELS_DIR, exist_ok=True)
os.environ["HF_HOME"] = os.path.join(_ROOT_MODELS, "hf_cache")

from faster_whisper import WhisperModel

print("Downloading faster-whisper 'small' model...")
model = WhisperModel("small", device="cpu", compute_type="int8", download_root=MODELS_DIR)
print("Whisper model ready. Cache dir:", MODELS_DIR)
