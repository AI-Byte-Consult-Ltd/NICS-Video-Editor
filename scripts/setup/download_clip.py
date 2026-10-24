"""Download CLIP ViT-B/32 (OpenAI weights) into the local project model cache."""
import os

MODELS_DIR = r"D:\NICS-VIDEO\models\clip"
os.makedirs(MODELS_DIR, exist_ok=True)
os.environ["HF_HOME"] = r"D:\NICS-VIDEO\models\hf_cache"

import open_clip

print("Downloading CLIP ViT-B-32 (openai weights)...")
model, _, preprocess = open_clip.create_model_and_transforms(
    "ViT-B-32", pretrained="openai", cache_dir=MODELS_DIR
)
tokenizer = open_clip.get_tokenizer("ViT-B-32")
print("CLIP model loaded OK. Cache dir:", MODELS_DIR)
print("Params:", sum(p.numel() for p in model.parameters()))
