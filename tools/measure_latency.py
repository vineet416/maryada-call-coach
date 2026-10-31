"""Latency measurement (docs/13 §6).

  python tools/measure_latency.py llm --n 30        LLM stage alone, HTTP/2 on vs off (no audio, no STT)
  python tools/measure_latency.py hero-report       latency and run-to-run variation from the recorded hero runs

Hero runs: start the backend with RECORD_RUNS=true, run tools/console_client.py c06 --quiet N times (sequential, one
Gnani request per key); every finished run is saved in data/replay/_runs/ and hero-report reads those files.

Run with the backend environment: backend/.venv/Scripts/python tools/measure_latency.py ...
Keys come from the environment only. Results are merged into data/eval/latency_runs.json.
"""
import argparse
import asyncio
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings
from app.rules import llm
from app.rules.schemas import CallContext, Turn

OUT = ROOT / "data" / "eval" / "latency_runs.json"


def pct(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(p * len(vals)))] if vals else 0.0


def summary(vals: list[float]) -> dict:
    return {"n": len(vals), "p50_ms": round(statistics.median(vals)) if vals else None,
            "p95_ms": round(pct(vals, 0.95)) if vals else None, "max_ms": round(max(vals)) if vals else None}


def agent_turns(n: int) -> list[tuple[CallContext, list[Turn], str]]:
    """Stored agent turns (c06 first, then others) with their two previous turns as context; at least 4 words."""
    items = []
    files = sorted((ROOT / "content" / "scenarios").glob("*.yaml"))
    for f in files:
        for sc in yaml.safe_load(f.read_text(encoding="utf-8"))["scenarios"]:
            ctx = CallContext(answered_by=sc.get("answered_by", "borrower"), simulated_start_time=sc.get("time", "12:00"))
            hist: list[Turn] = []
            for t in sc["turns"]:
                if t["s"] == "A" and len(t["t"].split()) >= llm.MIN_WORDS:
                    items.append((sc["id"] != "c06", ctx, list(hist), t["t"]))
                hist.append(Turn(speaker=t["s"], text=t["t"]))
    items.sort(key=lambda x: x[0])  # c06 turns first, stable otherwise
    return [(c, h, t) for _, c, h, t in items][:n]


def merge_out(key: str, value: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    cur[key] = value
    OUT.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")


async def llm_stage(n: int) -> None:
    """n calls per setting, alternating on/off call by call so network drift hits both equally."""
    turns = agent_turns(n)
    res: dict[str, list[float]] = {"http2_on": [], "http2_off": []}
    failed = {"http2_on": 0, "http2_off": 0}
    settings.llm_http2 = True
    on = llm.make_client()
    settings.llm_http2 = False
    off = llm.make_client()
    clients = {"http2_on": on, "http2_off": off}
    for name, c in clients.items():  # one warm-up each, not counted
        settings.llm_http2 = name == "http2_on"
        await llm.warm_up(c)
    for i, (ctx, hist, text) in enumerate(turns):
        for name in (("http2_on", "http2_off") if i % 2 == 0 else ("http2_off", "http2_on")):
            settings.llm_http2 = name == "http2_on"
            out, ms = await llm.review(clients[name], ctx, hist, text)
            if out is None:
                failed[name] += 1
            else:
                res[name].append(ms)
    await on.aclose()
    await off.aclose()
    settings.llm_http2 = True
    result = {k: {**summary(v), "failed": failed[k]} for k, v in res.items()}
    result["measured_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    result["model"] = settings.llm_model
    merge_out("llm_stage_http2", result)
    print(json.dumps(result, indent=1))


def load_runs(scenario: str = "c06") -> list[list[dict]]:
    files = sorted((ROOT / "data" / "replay" / "_runs").glob(f"{scenario}_*.json"), key=lambda f: f.stat().st_mtime)
    return [json.loads(f.read_text(encoding="utf-8"))["events"] for f in files]


def hero_report(turn: int = 7) -> None:
    runs = load_runs()
    fast, deep, seg_stt, deep_llm = [], [], [], []
    for evs in runs:
        seen = set()
        for e in evs:
            d = e["data"]
            if e["type"] == "transcript.final":
                seg_stt.append(d["stt_latency_ms"])
            elif e["type"] == "finding.detected" and d["kind"] == "violation":
                key = (d["turn_idx"], d["rule_id"], d["phase"])
                if key in seen:
                    continue  # first appearance of a rule per turn and phase
                seen.add(key)
                (fast if d["phase"] == "fast" else deep).append(d["latency"]["total_ms"])
                if d["phase"] == "deep":
                    deep_llm.append(d["latency"]["llm_ms"])
    result = {"runs": len(runs), "fast_path_ms": summary(fast), "deep_path_ms": summary(deep),
              "llm_ms_in_deep": summary(deep_llm), "prisma_segment_latency_ms": summary(seg_stt),
              "note": "total_ms = flag emitted minus segment end; segment end = first audio frame sent + summed vendor "
                      "audio_duration_ms (pauses between segments are not counted, so values are slightly high)"}
    hero_turn = {"fast_path_ms": summary([x["data"]["latency"]["total_ms"] for e in runs for x in [_first(e, turn, "fast")] if x]),
                 "deep_path_ms": summary([x["data"]["latency"]["total_ms"] for e in runs for x in [_first(e, turn, "deep")] if x])}
    result["hero_turn_first_violation"] = hero_turn
    merge_out("hero_runs", {**result, "measured_at": datetime.now(UTC).isoformat(timespec="seconds")})
    print(json.dumps(result, indent=1))
    print(f"\nVariation, first 5 runs, agent turn {turn}")
    for n, evs in enumerate(runs[:5], 1):
        fs = [(e["data"]["rule_id"], e["data"]["kind"][:4], tuple(e["data"]["token_range"]), e["data"]["source"],
               round(e["data"]["confidence"], 2)) for e in evs
              if e["type"] == "finding.detected" and e["data"]["turn_idx"] == turn and e["data"]["kind"] != "good_practice"]
        scores = [e["data"]["score"] for e in evs if e["type"] == "risk.update"]
        print(f"run {n}: findings={sorted(set(fs), key=lambda x: x[2])}\n       risk={scores}")


def _first(evs: list[dict], turn: int, phase: str) -> dict | None:
    return next((e for e in evs if e["type"] == "finding.detected" and e["data"]["turn_idx"] == turn
                 and e["data"]["phase"] == phase and e["data"]["kind"] == "violation"), None)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("llm").add_argument("--n", type=int, default=30)
    sub.add_parser("hero-report")
    a = ap.parse_args()
    if a.cmd == "llm":
        asyncio.run(llm_stage(a.n))
    else:
        hero_report()


if __name__ == "__main__":
    main()
