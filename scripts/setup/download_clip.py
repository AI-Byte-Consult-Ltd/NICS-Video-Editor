"""Download CLIP ViT-B/32 (OpenAI weights) into the local project model cache."""
import os
import sys

# Setup scripts are the only ones allowed online; set before config is
# imported, since config defaults the hub to offline mode.
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MODELS_DIR as _ROOT_MODELS

MODELS_DIR = os.path.join(_ROOT_MODELS, "clip")
os.makedirs(MODELS_DIR, exist_ok=True)
os.environ["HF_HOME"] = os.path.join(_ROOT_MODELS, "hf_cache")

import open_clip

print("Downloading CLIP ViT-B-32 (openai weights)...")
model, _, preprocess = open_clip.create_model_and_transforms(
    "ViT-B-32", pretrained="openai", cache_dir=MODELS_DIR
)
tokenizer = open_clip.get_tokenizer("ViT-B-32")
print("CLIP model loaded OK. Cache dir:", MODELS_DIR)
print("Params:", sum(p.numel() for p in model.parameters()))
