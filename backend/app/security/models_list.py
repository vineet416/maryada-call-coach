"""Clean a provider's model list into chat models only (OpenAI, Groq, OpenRouter, Gemini formats)."""
import json

NON_CHAT = ("embed", "whisper", "tts", "speech", "audio", "transcribe", "dall-e", "dalle", "image", "imagen", "veo",
            "moderation", "rerank", "guard", "realtime", "vision-preview", "aqa", "babbage", "davinci", "playai",
            "orpheus", "sora", "video", "ocr", "diffusion")


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
        mid = mid.removeprefix("models/")
        if _is_chat(mid, e):
            ids.add(mid)
    return sorted(ids, key=str.lower)
