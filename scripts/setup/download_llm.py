"""Download Qwen2.5-1.5B-Instruct GGUF (Q4_K_M quant) into the local project model cache."""
import os
import sys

# Setup scripts are the only ones allowed online; set before config is
# imported, since config defaults the hub to offline mode.
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MODELS_DIR as _ROOT_MODELS

MODELS_DIR = os.path.join(_ROOT_MODELS, "llm")
os.makedirs(MODELS_DIR, exist_ok=True)

from huggingface_hub import hf_hub_download

print("Downloading Qwen2.5-1.5B-Instruct-GGUF (Q4_K_M)...")
path = hf_hub_download(
    repo_id="Qwen/Qwen2.5-1.5B-Instruct-GGUF",
    filename="qwen2.5-1.5b-instruct-q4_k_m.gguf",
    local_dir=MODELS_DIR,
)
print("Downloaded to:", path)
print("Size MB:", round(os.path.getsize(path) / 1024 / 1024, 1))
