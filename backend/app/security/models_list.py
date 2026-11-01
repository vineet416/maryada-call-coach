"""Clean a provider's model list into chat models only (OpenAI, Groq, OpenRouter, Gemini formats)."""
import json

NON_CHAT = ("embed", "whisper", "tts", "speech", "audio", "transcribe", "dall-e", "dalle", "image", "imagen", "veo",
            "moderation", "rerank", "guard", "realtime", "vision-preview", "aqa", "babbage", "davinci", "playai",
            "orpheus", "sora", "video", "ocr", "diffusion")

# Listed by the provider but answered "404" or "400" to a chat request when probed with a real key on 2026-11-01.
# Keep this short; add an id only after a probe shows it fails (a 429 is not a reason).
DENY_MODELS = frozenset({
    "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro",  # 404, retired
    "antigravity-preview-05-2026", "antigravity-preview-09-2026", "antigravity-preview-latest",  # 400
})

# Gemini lists many models that are not chat models (image, speech, live, robotics, agents). For that provider only, an id
# is shown when its name says "gemini-" and none of these words. This is a name check, not proof that a model works on a
# free key.
GEMINI_SKIP = ("image", "tts", "audio", "live", "embedding", "embed", "robotics", "computer-use", "deep-research",
               "imagen", "veo", "aqa")


def _gemini_chat_name(model_id: str) -> bool:
    low = model_id.lower()
    return low.startswith("gemini-") and not any(w in low for w in GEMINI_SKIP)


def _is_chat(model_id: str, entry: dict) -> bool:
    low = model_id.lower()
    if any(w in low for w in NON_CHAT):
        return False
    methods = entry.get("supportedGenerationMethods")  # native Gemini listing
    if isinstance(methods, list) and "generateContent" not in methods:
        return False
    out = (entry.get("architecture") or {}).get("output_modalities")  # OpenRouter
    return not (isinstance(out, list) and out and "text" not in out)


def clean_models(raw: bytes | str | dict) -> list[str]:
    """Sorted, de-duplicated chat model ids. Raises ValueError when the reply is not a model list."""
    try:
        doc = raw if isinstance(raw, dict) else json.loads(raw)
    except ValueError:
        raise ValueError("not json") from None
    items = doc.get("data") if isinstance(doc, dict) else None
    if items is None and isinstance(doc, dict):
        items = doc.get("models")
    if not isinstance(items, list):
        raise ValueError("not a model list")  # noqa: TRY004
    ids: set[str] = set()
    for e in items:
        if isinstance(e, str):
            e = {"id": e}
        if not isinstance(e, dict):
            continue
        mid = e.get("id") or e.get("name")
        if not isinstance(mid, str) or not mid:
            continue
        gemini = mid.startswith("models/")  # only the Gemini listing prefixes its ids with "models/"
        mid = mid.removeprefix("models/")
        if gemini and not _gemini_chat_name(mid):
            continue
        if mid not in DENY_MODELS and _is_chat(mid, e):
            ids.add(mid)
    return sorted(ids, key=str.lower)
