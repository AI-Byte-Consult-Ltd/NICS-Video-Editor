"""Zero-shot frame tagging via CLIP. Honest limitation: this is similarity
between a frame and a fixed English tag vocabulary / the prompt text — it is
NOT scene captioning and does not know plot, names, or causal events. CLIP's
text tower is English-trained, so matching against non-English prompts is
weaker and treated as a secondary signal, never the sole basis for a decision."""
import os

from config import CLIP_MODEL_DIR, MODELS_DIR

os.environ.setdefault("HF_HOME", os.path.join(MODELS_DIR, "hf_cache"))

import cv2
import torch
import open_clip

TAG_VOCAB = [
    "beach", "ocean", "swimming", "boat", "mountain", "forest", "jungle",
    "city street", "old town architecture", "temple", "market", "food",
    "restaurant", "nightlife", "sunset", "sunrise", "driving a car", "scooter riding",
    "walking", "hiking", "crowd of people", "friends group photo", "selfie",
    "animal", "waterfall", "swimming pool", "airport", "plane window view",
    "hotel room", "street food stall", "local people", "boat trip", "island",
    "snorkeling or diving", "rooftop view", "cityscape at night", "rural village",
    "desert", "snow or mountains", "river", "bridge", "statue or monument",
]

TAG_VOCAB_RU = {
    "beach": "пляж", "ocean": "океан", "swimming": "купание", "boat": "лодка",
    "mountain": "горы", "forest": "лес", "jungle": "джунгли", "city street": "городская улица",
    "old town architecture": "старый город", "temple": "храм", "market": "рынок", "food": "еда",
    "restaurant": "ресторан", "nightlife": "ночная жизнь", "sunset": "закат", "sunrise": "рассвет",
    "driving a car": "поездка на машине", "scooter riding": "поездка на скутере",
    "walking": "прогулка", "hiking": "поход в горы", "crowd of people": "толпа людей",
    "friends group photo": "фото с друзьями", "selfie": "селфи", "animal": "животное",
    "waterfall": "водопад", "swimming pool": "бассейн", "airport": "аэропорт",
    "plane window view": "вид из самолёта", "hotel room": "номер отеля",
    "street food stall": "уличная еда", "local people": "местные жители",
    "boat trip": "поездка на лодке", "island": "остров", "snorkeling or diving": "дайвинг",
    "rooftop view": "вид с крыши", "cityscape at night": "ночной город",
    "rural village": "деревня", "desert": "пустыня", "snow or mountains": "снежные горы",
    "river": "река", "bridge": "мост", "statue or monument": "памятник",
}

_model = None
_preprocess = None
_tokenizer = None
_device = "cpu"


def _load():
    global _model, _preprocess, _tokenizer
    if _model is not None:
        return
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32-quickgelu", pretrained="openai", cache_dir=CLIP_MODEL_DIR
    )
    model.eval()
    _model = model
    _preprocess = preprocess
    _tokenizer = open_clip.get_tokenizer("ViT-B-32-quickgelu")


def _bgr_to_pil(frame):
    from PIL import Image
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def embed_image(frame):
    _load()
    img = _preprocess(_bgr_to_pil(frame)).unsqueeze(0)
    with torch.no_grad():
        feat = _model.encode_image(img)
        feat /= feat.norm(dim=-1, keepdim=True)
    return feat[0]


_vocab_embeds = None


def _vocab_embeddings():
    global _vocab_embeds
    if _vocab_embeds is not None:
        return _vocab_embeds
    _load()
    tokens = _tokenizer(TAG_VOCAB)
    with torch.no_grad():
        feats = _model.encode_text(tokens)
        feats /= feats.norm(dim=-1, keepdim=True)
    _vocab_embeds = feats
    return feats


def embed_text(text):
    _load()
    tokens = _tokenizer([text])
    with torch.no_grad():
        feat = _model.encode_text(tokens)
        feat /= feat.norm(dim=-1, keepdim=True)
    return feat[0]


def tag_frame(frame, top_k=4, min_similarity=0.20):
    img_feat = embed_image(frame)
    vocab = _vocab_embeddings()
    sims = (vocab @ img_feat).tolist()
    ranked = sorted(zip(TAG_VOCAB, sims), key=lambda x: -x[1])
    return [{"tag": t, "similarity": round(s, 3)} for t, s in ranked[:top_k] if s >= min_similarity]


def prompt_similarity(frame, prompt_text):
    if not prompt_text:
        return None
    img_feat = embed_image(frame)
    txt_feat = embed_text(prompt_text)
    return round(float(img_feat @ txt_feat), 3)
