"""Run the LLM stage on the hero call c06 twice in one process (cache and skip check; no STT, no audio).

Per agent segment (cumulative turn text, as the live pipeline sends it): the guarded skip is applied, then
app.rules.llm.review runs through its in-memory cache. Run 2 should cost 0 tokens. Stops before a call that could pass
the token limit. The API key is read through the app settings and never printed.

  backend/.venv/Scripts/python.exe tools/llm_cache_check.py [--limit 16000]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import yaml
from app.config import settings
from app.rules import llm
from app.rules.engine import deep_findings, fast_findings
from app.rules.schemas import CallContext, Turn
from app.rules.skip import should_skip
from app.session import assets

EST_NEXT_CALL = 1000


def segments():
    ev = json.loads((ROOT / "data/replay/c06.json").read_text(encoding="utf-8"))["events"]
    segs = [e["data"] for e in ev if e["type"] == "transcript.final"]
    spk = {t["idx"]: t["speaker"] for t in assets.audio_manifest()["c06"]["turns"]}
    history, out = [], []
    for idx in sorted({s["turn_idx"] for s in segs}):
        text = ""
        for s in (s for s in segs if s["turn_idx"] == idx):
            text = f"{text} {s['text']}".strip()
            if spk[idx] == "A" and s["text"]:
                out.append((idx, s["segment_idx"], list(history), text))
        history.append(Turn(speaker=spk[idx], text=text))
    return out


async def run(label: str, ctx: CallContext, limit: int) -> dict:
    t0, c0, h0 = llm.STATS["tokens"], llm.STATS["calls"], llm.STATS["cache_hits"]
    skipped, rows = 0, []
    client = llm.make_client()
    try:
        for idx, seg, hist, text in segments():
            fast = fast_findings(ctx, hist, idx, text)
            if should_skip(ctx, hist, text, fast):
                skipped += 1
                rows.append((idx, seg, len(text.split()), "SKIPPED", []))
                continue
            if llm.STATS["tokens"] + EST_NEXT_CALL > limit and not _cached(ctx, hist, text):
                print(f"{label}: stopping, token limit {limit} would be passed")
                break
            out, ms = await llm.review(client, ctx, hist[-2:], text)
            if out is None:
                rows.append((idx, seg, len(text.split()), "LLM-FAILED", []))
                continue
            fs = deep_findings(ctx, fast, out, idx, text)
            rows.append((idx, seg, len(text.split()), f"{ms} ms", [(f.rule_id, f.kind, round(f.confidence, 2)) for f in fs]))
    finally:
        await client.aclose()
    res = {"tokens": llm.STATS["tokens"] - t0, "calls": llm.STATS["calls"] - c0,
           "cache_hits": llm.STATS["cache_hits"] - h0, "skipped": skipped, "rows": rows}
    print(f"\n{label}: tokens={res['tokens']} api_calls={res['calls']} cache_hits={res['cache_hits']} skipped={skipped}")
    for r in rows:
        print(f"  turn {r[0]} seg {r[1]} words {r[2]:>3} {r[3]:>10} {r[4]}")
    return res


def _cached(ctx, hist, text) -> bool:
    k = llm.cache_key(settings.llm_model, settings.euri_base_url, llm._messages(ctx, hist[-2:], text))
    return k in llm._CACHE


async def main(limit: int) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    settings.server_keys_enabled = True  # evaluation tool: uses the local env keys
    if not settings.euri_api_key:
        sys.exit("no local LLM key configured")
    sc = next(c for p in sorted((ROOT / "content" / "scenarios").glob("*.yaml"))
              for c in yaml.safe_load(p.read_text(encoding="utf-8"))["scenarios"] if c["id"] == "c06")
    ctx = CallContext(answered_by=sc["answered_by"], simulated_start_time=sc["time"])
    r1 = await run("run 1", ctx, limit)
    r2 = await run("run 2 (same process)", ctx, limit)
    print(f"\ntotal tokens this process: {llm.STATS['tokens']} (limit {limit})")
    print("run 2 findings identical to run 1:", [r[4] for r in r1["rows"]] == [r[4] for r in r2["rows"]])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=16000)
    asyncio.run(main(ap.parse_args().limit))
