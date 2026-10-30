"""Project spike (docs/06 section 1): STT settings, Timbre and Euri behaviour, latencies.

Run with the backend environment:  backend/.venv/Scripts/python tools/spike.py
Test lines come from content/scenarios (synthetic). Keys come from the environment only and are never printed.
Output: tables on stdout and data/audio/_cache/spike/results.json (git-ignored).
"""
import asyncio
import hashlib
import io
import json
import re
import statistics
import sys
import time
import wave
from pathlib import Path

import httpx2 as httpx
import websockets
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings

CACHE = ROOT / "data" / "audio" / "_cache" / "spike"
MODEL_STT = "prisma-v3.0"
AUDIO_CFG = {"encoding": "linear_pcm", "sample_rate": 8000, "container": "wav"}
VOICE = {"A": ("Prakash", 1.0), "B": ("Devansh", 0.95)}
HINTS = ["Tarang", "Finserv", "EMI", "police", "mohalle", "defaulter", "Court", "notice", "naukri", "payment", "record"]
CANDIDATES = "hi-IN,mr-IN,en-IN"
FRAME = 1024  # bytes: 64 ms of 8 kHz PCM16 mono
TTS_SLOTS = asyncio.Semaphore(1)  # the API allows one active TTS request at a time (docs/11 assumed 4)


# ---------- test lines ----------
def load_lines(per_role: int = 10) -> list[dict]:
    """Agent lines prefer labelled turns; borrower lines are taken in order. Each unique."""
    agent_l, agent_u, borrower = [], [], []
    for f in sorted((ROOT / "content" / "scenarios").glob("*.yaml")):
        for sc in yaml.safe_load(f.read_text(encoding="utf-8"))["scenarios"]:
            for t in sc["turns"]:
                if t["s"] == "A":
                    (agent_l if t.get("L") else agent_u).append(t["t"])
                elif t["s"] == "B":
                    borrower.append(t["t"])
    agents = list(dict.fromkeys(agent_l + agent_u))[:per_role]
    borrowers = [b for b in dict.fromkeys(borrower) if len(b.split()) >= 6][:per_role]
    return [{"role": r, "text": t, "terms": key_terms(t)} for r, ts in (("A", agents), ("B", borrowers)) for t in ts]


def key_terms(text: str, cap: int = 5) -> list[str]:
    words = [w for w in re.findall(r"[\w']+", text) if len(w) >= 4]
    hinted = [w for w in words if any(h.lower() in w.lower() for h in HINTS)]
    longest = sorted(dict.fromkeys(words), key=len, reverse=True)
    return list(dict.fromkeys(hinted + longest))[:cap]


# ---------- scoring: consonant skeleton works for Roman and Devanagari alike ----------
_DEV = {**dict.fromkeys("कख", "k"), **dict.fromkeys("गघ", "g"), **dict.fromkeys("चछ", "c"), **dict.fromkeys("जझज़", "j"),
        **dict.fromkeys("टठतथ", "t"), **dict.fromkeys("डढदधड़ढ़", "d"), **dict.fromkeys("णन", "n"),
        "प": "p", "फ": "f", "फ़": "f", **dict.fromkeys("बभ", "b"), "म": "m", "र": "r", "ल": "l", "ळ": "l", "व": "v",
        **dict.fromkeys("शषस", "s"), "ह": "", "य": ""}


def skeleton(word: str) -> str:
    w = word.lower()
    if re.search(r"[ऀ-ॿ]", w):
        out = "".join(_DEV.get(ch, "") for ch in w)
    else:
        w = re.sub(r"(kh|gh|ch|th|dh|ph|bh|sh)", lambda m: m.group(1)[0], w)
        w = w.replace("w", "v").replace("z", "j").replace("q", "k").replace("x", "ks")
        out = re.sub(r"[aeiouyh\W\d_]", "", w)
    return re.sub(r"(.)\1+", r"\1", out)


def edit1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1 or min(len(a), len(b)) < 3:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    s, l = sorted((a, b), key=len)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def recovery(terms: list[str], transcript: str) -> float:
    if not terms:
        return 1.0
    got = {skeleton(w) for w in re.findall(r"[\wऀ-ॿ']+", transcript)}
    return sum(any(edit1(skeleton(t), g) for g in got if g) for t in terms) / len(terms)


# ---------- TTS ----------
async def tts(client: httpx.AsyncClient, line: dict, extra: dict | None = None) -> bytes:
    voice, speed = VOICE[line["role"]]
    body = {"text": line["text"], "voice": voice, "model": "timbre-v3.0", "language": "hi-IN", "speed": speed,
            "audio_config": AUDIO_CFG, **(extra or {})}
    key = CACHE / (hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:24] + ".wav")
    if key.exists():
        return key.read_bytes()
    for attempt in range(6):
        async with TTS_SLOTS:
            r = await client.post(settings.gnani_tts_url, headers={"x-api-key-id": settings.gnani_api_key_id}, json=body)
        if r.status_code not in (429, 500, 502, 503):
            break
        await asyncio.sleep(10 * (attempt + 1))  # per-minute limit: wait it out
    if r.status_code != 200:
        raise RuntimeError(f"TTS {r.status_code} for {line['text'][:40]!r}: {r.text[:200]}")
    key.write_bytes(r.content)
    return r.content


async def timbre_checks(client: httpx.AsyncClient) -> dict:
    """Request format facts: sample rate, audio tags, character limit, voice/model pairing."""
    hdr = {"x-api-key-id": settings.gnani_api_key_id}
    base = {"voice": "Prakash", "model": "timbre-v3.0", "language": "hi-IN", "speed": 1.0, "audio_config": AUDIO_CFG}
    res: dict = {}
    for name, text in [("plain", "Namaste, yeh ek test hai."), ("tag", "<angry> Namaste, yeh ek test hai."),
                       ("chars_700", ("Yeh ek test hai. " * 50)[:700]), ("chars_1000", ("Yeh ek test hai. " * 70)[:1000])]:
        r = await client.post(settings.gnani_tts_url, headers=hdr, json={**base, "text": text})
        res[name] = r.status_code if r.status_code != 200 else f"200 ({len(r.content)} bytes)"
        if name == "plain" and r.status_code == 200:
            with wave.open(io.BytesIO(r.content)) as w:
                res["wav_rate_channels_width"] = [w.getframerate(), w.getnchannels(), w.getsampwidth()]
        if r.status_code != 200:
            res[name] += f" {r.text[:120]}"
    r = await client.post(settings.gnani_tts_url, headers=hdr, json={**base, "text": "Test.", "model": "timbre-v2"})
    res["wrong_model"] = f"{r.status_code} {r.text[:120]}"
    return res


# ---------- STT: REST and realtime ----------
async def stt_rest(client: httpx.AsyncClient, wav: bytes, data: dict) -> tuple[str, float, str]:
    t0 = time.perf_counter()
    r = await client.post(settings.gnani_stt_rest_url, headers={"X-API-Key-ID": settings.gnani_api_key_id},
                          files={"audio_file": ("a.wav", wav, "audio/wav")}, data={"model": MODEL_STT, **data})
    if r.status_code != 200:
        return f"ERROR {r.status_code} {r.text[:160]}", 0.0, ""
    j = r.json()
    return j.get("transcript", ""), time.perf_counter() - t0, j.get("detected_language_code", "")


async def stt_realtime(wav: bytes, lang: str, candidates: str | None) -> tuple[str, list[float], str]:
    with wave.open(io.BytesIO(wav)) as w:
        pcm = w.readframes(w.getnframes())
    hdr = {"x-api-key-id": settings.gnani_api_key_id, "model": MODEL_STT, "language_code": lang, "x-sample-rate": "8000"}
    if candidates:
        hdr["x-language-candidates"] = candidates
    texts, lats, det = [], [], ""
    try:
        async with websockets.connect(settings.gnani_stt_ws_url, additional_headers=hdr, open_timeout=15) as ws:
            await ws.recv()  # "connected"
            for i in range(0, len(pcm), FRAME):
                await ws.send(pcm[i:i + FRAME])
                await asyncio.sleep(len(pcm[i:i + FRAME]) / 16000 * settings.pace)
            await ws.send(json.dumps({"type": "commit"}))
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), 2.0))
                if m.get("type") == "transcript" and m.get("is_final"):
                    texts.append(m["text"])
                    lats.append(m.get("latency", 0) / 1000)
                    det = m.get("detected_language_code", det)
    except TimeoutError:
        pass
    except Exception as e:  # noqa: BLE001 - report any transport failure in the table
        return f"ERROR {type(e).__name__} {str(e)[:100]}", lats, det
    return " ".join(texts), lats, det


def pct(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(p * len(vals)))] if vals else 0.0


# ---------- Euri ----------
async def euri_latency(client: httpx.AsyncClient, lines: list[dict], n: int = 20) -> dict:
    url = settings.euri_base_url.rstrip("/") + "/chat/completions"
    hdr = {"Authorization": f"Bearer {settings.euri_api_key}"}
    out: dict = {"lat": [], "json_ok": 0, "errors": []}
    for i in range(n):
        body = {"model": settings.llm_model, "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": 'Reply with JSON only: {"findings":[{"rule_id":"","quote":""}]}. '
                              "Flag clear threats or false legal claims in the agent line; empty list if none."},
                             {"role": "user", "content": lines[i % len(lines)]["text"]}]}
        t0 = time.perf_counter()
        r = await client.post(url, headers=hdr, json=body)
        out["lat"].append(time.perf_counter() - t0)
        if r.status_code != 200:
            out["errors"].append(f"{r.status_code} {r.text[:120]}")
            continue
        try:
            json.loads(r.json()["choices"][0]["message"]["content"])
            out["json_ok"] += 1
        except (ValueError, KeyError, IndexError):
            out["errors"].append("invalid JSON content")
    lat = out.pop("lat")
    out.update(n=n, median_s=round(statistics.median(lat), 2), p95_s=round(pct(lat, 0.95), 2), max_s=round(max(lat), 2))
    out["errors"] = sorted(set(out["errors"]))[:3]
    return out


# ---------- main ----------
async def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    lines = load_lines()
    results: dict = {"lines": len(lines)}
    async with httpx.AsyncClient(timeout=90) as client:
        results["timbre"] = await timbre_checks(client)
        print("TIMBRE", json.dumps(results["timbre"], indent=1))
        wavs = await asyncio.gather(*(tts(client, ln) for ln in lines))

        rest_combos = {"A indic-auto+multi": {"language_code": "indic-auto", "multi_lang_codes": CANDIDATES},
                       "B indic-auto+multi hi,en": {"language_code": "indic-auto", "multi_lang_codes": "hi-IN,en-IN"},
                       "C hi-IN": {"language_code": "hi-IN"}, "D mr-IN": {"language_code": "mr-IN"},
                       "C hi-IN codemix": {"language_code": "hi-IN", "output_mode": "codemix"},
                       "C hi-IN transcribe": {"language_code": "hi-IN", "output_mode": "transcribe"},
                       "C hi-IN verbatim": {"language_code": "hi-IN", "output_mode": "verbatim"}}
        sem = asyncio.Semaphore(1)  # REST STT also allows one active request

        async def one(ln, wav, data):
            async with sem:
                return await stt_rest(client, wav, data)

        table: dict = {}
        for name, data in rest_combos.items():
            idx = [i for i, ln in enumerate(lines) if not (name.startswith("D") and ln["role"] == "A")]
            outs = await asyncio.gather(*(one(lines[i], wavs[i], data) for i in idx))
            errs = [o[0] for o in outs if o[0].startswith("ERROR")]
            row = {"errors": sorted(set(errs))[:2]}
            for role in "AB":
                sel = [(lines[i], o) for i, o in zip(idx, outs) if lines[i]["role"] == role and not o[0].startswith("ERROR")]
                row[role] = round(statistics.mean(recovery(ln["terms"], o[0]) for ln, o in sel), 3) if sel else None
            ok = [o[1] for o in outs if not o[0].startswith("ERROR")]
            row["latency_median_s"] = round(statistics.median(ok), 2) if ok else None
            table[name] = row
            print("REST", name, row)
        results["rest"] = table

        rt_combos = {"A indic-auto": ("indic-auto", None), "B indic-auto+candidates": ("indic-auto", CANDIDATES),
                     "C hi-IN": ("hi-IN", None)}
        rt: dict = {}
        for name, (lang, cand) in rt_combos.items():
            outs = await asyncio.gather(*(stt_realtime(w, lang, cand) for w in wavs))
            row = {"errors": sorted({o[0] for o in outs if o[0].startswith("ERROR")})[:2]}
            for role in "AB":
                sel = [(ln, o) for ln, o in zip(lines, outs) if ln["role"] == role and not o[0].startswith("ERROR")]
                row[role] = round(statistics.mean(recovery(ln["terms"], o[0]) for ln, o in sel), 3) if sel else None
            seg = [x for o in outs for x in o[1]]
            row["segment_latency_median_s"] = round(statistics.median(seg), 3) if seg else None
            row["segment_latency_p95_s"] = round(pct(seg, 0.95), 3)
            rt[name] = row
            print("REALTIME", name, row)
        results["realtime"] = rt

        results["euri"] = await euri_latency(client, [ln for ln in lines if ln["role"] == "A"])
        print("EURI", results["euri"])
    (CACHE / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
