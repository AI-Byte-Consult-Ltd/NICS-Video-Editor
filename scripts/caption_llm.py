"""Grounded caption generation. The LLM is given only facts extracted by
analysis (CLIP tags, transcript snippets, style/mood) and asked to phrase
them as a short caption in ONE language per call — it is instructed not to
invent events, names, or details absent from those facts. If the LLM is
unavailable or produces something malformed, falls back to a template
caption built directly from the same facts (never fabricated)."""
import json
import re

from config import LLM_MODEL_PATH
from semantic import TAG_VOCAB_RU


_ALLOWED_CHARS = {
    "ru": re.compile(r"[^Ѐ-ӿ0-9\s,.!?;:'\"\-—()]"),
    "en": re.compile(r"[^a-zA-Z0-9\s,.!?;:'\"\-’()]"),
}


def _has_disallowed_chars(text, language):
    pattern = _ALLOWED_CHARS.get(language)
    return bool(pattern.search(text)) if pattern else False


_llm = None
_llm_failed = False


def _load():
    global _llm, _llm_failed
    if _llm is not None or _llm_failed:
        return _llm
    try:
        from llama_cpp import Llama
        _llm = Llama(model_path=LLM_MODEL_PATH, n_ctx=2048, n_threads=8, verbose=False)
    except Exception:
        _llm_failed = True
        _llm = None
    return _llm


_SYSTEM = {
    "ru": (
        "Ты пишешь короткую подпись для видео-ролика (травел/лайфстайл шортс). "
        "Тебе даны ТОЛЬКО факты (визуальные теги, возможно фрагмент речи). "
        "Никогда не выдумывай события, имена или детали, которых нет в фактах. "
        "Пиши по-русски просто, грамотно, без ошибок, короткой естественной фразой "
        "(не длиннее 6 слов), как в примерах. Строго JSON: {\"caption\": \"...\"}.\n"
        "Примеры:\n"
        "Факты: теги=[beach, ocean] -> {\"caption\": \"Пляж и бескрайний океан\"}\n"
        "Факты: теги=[city street, walking] -> {\"caption\": \"Прогулка по городским улицам\"}\n"
        "Факты: теги=[] -> {\"caption\": \"Момент путешествия\"}"
    ),
    "en": (
        "You write a short on-screen caption for a travel/lifestyle short video. "
        "You are given ONLY facts (visual tags, maybe a speech snippet). "
        "Never invent events, names, or details absent from the facts. "
        "Write natural, grammatically correct English, a short simple phrase "
        "(max 6 words), like the examples. Strict JSON: {\"caption\": \"...\"}.\n"
        "Examples:\n"
        "Facts: tags=[beach, ocean] -> {\"caption\": \"Beach and endless ocean\"}\n"
        "Facts: tags=[city street, walking] -> {\"caption\": \"Walking the city streets\"}\n"
        "Facts: tags=[] -> {\"caption\": \"A travel moment\"}"
    ),
}


def _is_sane(text, language, max_words=7, max_token_len=16):
    words = text.split()
    if not words or len(words) > max_words:
        return False
    if any(len(w.strip(",.!?;:'\"")) > max_token_len for w in words):
        return False
    if _has_disallowed_chars(text, language):
        return False
    return True


def _fallback_caption(facts, language, mood_ru="путешествие", mood_en="the journey"):
    tags = facts.get("tags") or []
    if tags:
        tag = tags[0]
        if language == "ru":
            text = f"Момент: {TAG_VOCAB_RU.get(tag, tag)}"
        else:
            text = f"Moment: {tag}"
    else:
        text = f"Кадр из {mood_ru}" if language == "ru" else f"A moment from {mood_en}"
    return {language: text}


def generate_caption(facts, role="segment", language="ru", language_tone="neutral"):
    """facts: {"tags": [...], "transcript": "...", "style": "...", "role": "intro/mid/outro"}
    Returns a single-key dict: {"ru": "..."} or {"en": "..."}."""
    llm = _load()
    if llm is None:
        return _fallback_caption(facts, language)

    user_prompt = (
        f"Facts: {json.dumps(facts, ensure_ascii=False)}\n"
        f"Caption role: {role}. Tone: {language_tone}.\n"
        "Respond with the JSON object only."
    )
    try:
        resp = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM[language]},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=60,
            temperature=0.35,
        )
        text = resp["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return _fallback_caption(facts, language)
        data = json.loads(match.group(0))
        caption = (data.get("caption") or "").strip()
        if not caption or not _is_sane(caption, language):
            return _fallback_caption(facts, language)
        return {language: caption}
    except Exception:
        return _fallback_caption(facts, language)
