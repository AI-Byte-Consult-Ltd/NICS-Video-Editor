"""Download Qwen2.5-1.5B-Instruct GGUF (Q4_K_M quant) into the local project model cache."""
import os

MODELS_DIR = r"D:\NICS-VIDEO\models\llm"
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
