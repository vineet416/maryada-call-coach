"""Evaluation run: 30 calls x noise conditions through Gnani REST STT and the production rule engine, scored against the labels.

Unit = (call, agent turn, rule); see tools/eval_scoring.py. The rule engine is the production code with the production
thresholds (0.75 / 0.45), the guarded skip and the production model; it runs once per complete agent turn.
Modes: `full` (prefilter + gates + language model) and `rules_only` (the ablation: prefilter + gates, no language model, no
Euri call at all). Conditions, in order: clean, snr10, snr20, snr5.

Resumable: each (mode, condition, call) result is written to data/eval/runs/<mode>/<condition>/<call>.json and skipped on
the next run when its labels hash matches. STT transcripts are cached by audio hash (data/eval/transcripts_cache/); language
model answers by (model, endpoint, prompt hash) (data/eval/llm_cache.jsonl). A Gnani auth error, a Euri 403/429 or the
token cap stops the run cleanly (nothing half-written); run it again later to continue.

  backend/.venv/Scripts/python.exe tools/run_eval.py --mode rules_only --conditions clean
  backend/.venv/Scripts/python.exe tools/run_eval.py --mode full --conditions clean,snr10 --limit 3 --max-tokens 20000
  backend/.venv/Scripts/python.exe tools/run_eval.py --report --mode rules_only --conditions clean
  backend/.venv/Scripts/python.exe tools/run_eval.py --estimate

Keys come from the app settings (environment); they are never printed or written.
"""
import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))
import eval_scoring as es
import httpx2 as httpx
import yaml
from app.config import settings
from app.rules import engine, llm, skip
from app.rules.engine import REVIEW_MIN, VIOLATION_MIN, deep_findings, fast_findings
from app.rules.schemas import Turn
from app.session import assets
from app.stt import rest
from app.stt.base import SttAuthError, SttError, load_profile

CONDITIONS = ("clean", "snr10", "snr20", "snr5")
EVAL = settings.data_dir / "eval"
CACHE = EVAL / "transcripts_cache"
RUNS = EVAL / "runs"
LLM_CACHE = EVAL / "llm_cache.jsonl"
RESULTS = EVAL / "eval_results.json"
STT_TIMEOUT_S, LLM_TIMEOUT_S, STT_TRIES = 60.0, 30.0, 3
TOKENS_PER_REQUEST = 904  # measured on the hero call (docs/EVAL-NOTES.md: 10,849 tokens / 12 requests)


class Stop(Exception):
    """Clean stop: the reason is printed, finished calls are kept, the unfinished call is not written."""


def say(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- STT
def stt_cache_path(wav: Path, profile: dict) -> Path:
    h = hashlib.sha256(wav.read_bytes())
    h.update(f"|{profile['model']}|{profile['language_code']}|rest".encode())
    return CACHE / f"{h.hexdigest()[:24]}.json"


async def transcribe(client: httpx.AsyncClient, wav: Path, profile: dict, key: str, st: dict) -> dict:
    """Transcript of one turn: cache first, else one Gnani REST request (bounded retries). Empty text is never cached."""
    path = stt_cache_path(wav, profile)
    if path.exists():
        st["cached"] += 1
        return json.loads(path.read_text(encoding="utf-8"))
    err = ""
    for attempt in range(STT_TRIES):
        try:
            segs = await asyncio.wait_for(rest.transcribe_turn(client, wav, profile, key), STT_TIMEOUT_S)
        except SttAuthError as e:
            raise Stop(f"Gnani refused the key ({e}); nothing more to transcribe") from e
        except (SttError, TimeoutError) as e:
            err = str(e) or type(e).__name__
            await asyncio.sleep(3 * (attempt + 1))
            continue
        out = {"text": " ".join(s.text for s in segs).strip(), "lang": segs[0].lang if segs else "",
               "latency_ms": max((s.latency_ms for s in segs), default=0)}
        st["requests"] += 1
        st["latency_ms"] += out["latency_ms"]
        if out["text"]:
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out
    raise Stop(f"Gnani STT failed {STT_TRIES} times in a row ({err})")


# ---------------------------------------------------------------- language model
async def review(client: httpx.AsyncClient, ctx, hist: list[Turn], text: str, st: dict, budget: int | None):
    """Same prompt, model, fallback and cache key as app.rules.llm.review; a 403/429 stops the run instead of degrading."""
    messages = llm._messages(ctx, hist, text)
    for model in (settings.llm_model, settings.llm_fallback_model):
        ck = llm.cache_key(model, settings.euri_base_url, messages)
        if ck in llm._CACHE and (out := engine.parse_llm(llm._CACHE[ck])) is not None:
            st["cache_hits"] += 1
            return out
        if budget is not None and llm.STATS["tokens"] + TOKENS_PER_REQUEST > budget:
            raise Stop(f"token cap {budget} reached ({llm.STATS['tokens']} used in this run)")
        try:
            raw, _ = await asyncio.wait_for(llm.chat(client, model, messages, None), LLM_TIMEOUT_S)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403, 429):
                raise Stop(f"Euri answered {e.response.status_code}; key refused, allowance used up or rate limited") from e
            continue
        except (TimeoutError, httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
            continue
        out = engine.parse_llm(raw)
        if out is not None:
            llm._cache_put(ck, raw)
            st["requests"] += 1
            return out
    st["degraded"] += 1
    return None


# ---------------------------------------------------------------- one call
def turn_wav(cid: str, cond: str, idx: int, manifest_turn: dict) -> Path:
    if cond == "clean":
        return settings.data_dir / "audio" / manifest_turn["wav8k"]
    return EVAL / "audio" / cond / cid / f"{idx}.wav"


def finding_row(cid: str, f) -> dict:
    return {"call": cid, "turn": f.turn_idx, "rule": f.rule_id, "kind": f.kind, "confidence": round(f.confidence, 3),
            "source": f.source, "quote": f.quote}


async def run_call(sc: dict, cond: str, mode: str, labels_h: str, clients: dict, key: str, budget: int | None) -> dict:
    cid = sc["id"]
    manifest = assets.audio_manifest()[cid]["turns"]
    if len(manifest) != len(sc["turns"]) or [t["idx"] for t in manifest] != list(range(1, len(manifest) + 1)):
        raise ValueError(f"{cid}: audio manifest does not match the script")
    ctx = assets.context_for(sc)
    stt = {"requests": 0, "cached": 0, "latency_ms": 0}
    lm = {"requests": 0, "cache_hits": 0, "skipped": 0, "degraded": 0, "tokens": 0}
    tok0 = llm.STATS["tokens"]
    history: list[Turn] = []
    turns, dets = [], []
    for i, (t, mt) in enumerate(zip(sc["turns"], manifest, strict=True), 1):
        profile = load_profile(assets.SPEAKER[t["s"]])
        tr = await transcribe(clients["stt"], turn_wav(cid, cond, i, mt), profile, key, stt)
        text = tr["text"]
        turns.append({"idx": i, "speaker": t["s"], "text": text, "stt_ms": tr["latency_ms"], "lang": tr["lang"]})
        if t["s"] == "A":
            fast = fast_findings(ctx, history, i, text)
            found = fast
            if mode == "full" and text.strip():
                if skip.should_skip(ctx, history, text, fast):
                    lm["skipped"] += 1
                else:
                    out = await review(clients["llm"], ctx, history[-2:], text, lm, budget)
                    found = deep_findings(ctx, fast, out, i, text)
            dets += [finding_row(cid, f) for f in found]
        history.append(Turn(speaker=t["s"], text=text))
    lm["tokens"] = llm.STATS["tokens"] - tok0
    return {"schema": 1, "call_id": cid, "condition": cond, "mode": mode, "labels_hash": labels_h,
            "engine": engine_block(mode),
            "stt": {**stt, "model": load_profile("agent")["model"], "path": "rest"}, "llm": lm, "turns": turns,
            "detections": dets, "completed_at": datetime.now(UTC).isoformat(timespec="seconds")}


def engine_block(mode: str) -> dict:
    """What the engine was when a result was made: thresholds, skip, model, and a hash of the rule files and the prompt."""
    h = hashlib.sha256()
    for name in ("rules.yaml", "rules_phrases.yaml"):
        h.update((settings.content_dir / name).read_bytes())
    h.update(llm.system_prompt().encode())
    return {"violation_min": VIOLATION_MIN, "review_min": REVIEW_MIN, "skip_words": settings.skip_llm_max_words,
            "llm_model": settings.llm_model if mode == "full" else None, "rules_prompt_hash": h.hexdigest()[:16]}


def run_path(mode: str, cond: str, cid: str) -> Path:
    return RUNS / mode / cond / f"{cid}.json"


def load_run(mode: str, cond: str, cid: str, labels_h: str) -> dict | None:
    p = run_path(mode, cond, cid)
    if not p.exists():
        return None
    r = json.loads(p.read_text(encoding="utf-8"))
    return r if r.get("labels_hash") == labels_h and r.get("engine") == engine_block(mode) else None  # else: stale, run again


def save_run(r: dict) -> None:
    p = run_path(r["mode"], r["condition"], r["call_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


# ---------------------------------------------------------------- aggregate and report
def split() -> dict:
    return yaml.safe_load((settings.content_dir / "split.yaml").read_text(encoding="utf-8"))


def aggregate(scenarios: list[dict], mode: str, cond: str, labels_h: str) -> dict | None:
    """Scores over the calls whose result exists for (mode, cond). None when no call has run."""
    runs = {sc["id"]: load_run(mode, cond, sc["id"], labels_h) for sc in scenarios}
    done = sorted(c for c, r in runs.items() if r)
    if not done:
        return None
    dets = [d for c in done for d in runs[c]["detections"]]
    sp = split()
    out = {"calls_run": len(done), "complete": len(done) == len(scenarios), "all": es.score(scenarios, dets, done)}
    for name in ("tune", "held_out"):
        ids = [c for c in done if c in sp[name]]
        out[name] = es.score(scenarios, dets, ids) if ids else None
    n_stt = sum(runs[c]["stt"]["requests"] + runs[c]["stt"]["cached"] for c in done)
    out["stt"] = {"turns": n_stt, "requests_made": sum(runs[c]["stt"]["requests"] for c in done),
                  "avg_latency_ms": round(sum(runs[c]["stt"]["latency_ms"] for c in done)
                                          / max(1, sum(runs[c]["stt"]["requests"] for c in done)))}
    out["llm"] = {k: sum(runs[c]["llm"][k] for c in done) for k in ("requests", "cache_hits", "skipped", "degraded", "tokens")}
    return out


def write_results(scenarios: list[dict], labels_h: str) -> dict:
    res = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "labels_hash": labels_h,
           "n_calls": len(scenarios), "conditions": list(CONDITIONS),
           "model_info": {"stt": "Gnani Prisma V3.0 (REST, one request per turn)", "llm": settings.llm_model,
                          "thresholds": {"violation": VIOLATION_MIN, "needs_review": REVIEW_MIN}},
           "full": {}, "ablation_llm_off": {}}
    for mode, key in (("full", "full"), ("rules_only", "ablation_llm_off")):
        for cond in CONDITIONS:
            if (a := aggregate(scenarios, mode, cond, labels_h)) is not None:
                res[key][cond] = a
    parts = [v["complete"] for k in ("full", "ablation_llm_off") for v in res[k].values()]
    res["status"] = "complete" if res["full"] and all(parts) else "partial"
    RESULTS.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def f(x: float | None) -> str:
    return "  -  " if x is None else f"{x:5.2f}"


def units(us: list) -> str:
    return " ".join(f"t{u[1]}{u[2]}" for u in us) or "-"


def print_report(a: dict, title: str) -> None:
    say(f"\n=== {title}: {a['calls_run']} calls{'' if a['complete'] else ' (INCOMPLETE)'} ===")
    for label, key in (("ALL CALLS", "all"), ("TUNE SET", "tune"), ("HELD-OUT SET", "held_out")):
        s = a[key]
        if s is None:
            continue
        say(f"\n--- {label} ({s['n_calls']} calls) ---")
        say("rule | strict: P     R     F1    TP FP FN | with review: P     R     F1    TP FP FN | needs_review on/off label")
        for r in (*es.RULES, "ALL"):
            b = s["overall"] if r == "ALL" else s["per_rule"][r]
            x, y, n = b["strict"], b["with_review"], b["needs_review"]
            say(f"{r:4} |         {f(x['p'])} {f(x['r'])} {f(x['f1'])}  {x['tp']:2} {x['fp']:2} {x['fn']:2} |"
                f"              {f(y['p'])} {f(y['r'])} {f(y['f1'])}  {y['tp']:2} {y['fp']:2} {y['fn']:2} | {n['on_label']}/{n['off_label']}")
        cl, ng, g1 = s["call_level"], s["negatives"], s["g1"]
        say(f"call-level recall (expected rule caught at least once): strict {cl['caught']}/{cl['expected']}, "
            f"with review {cl['caught_with_review']}/{cl['expected']}")
        say(f"calls without labels: {ng['calls']}; with a false alarm: strict {ng['calls_with_false_alarm']}, "
            f"with review {ng['calls_with_false_alarm_with_review']} ({ng['false_alarm_units']} strict units)")
        say(f"G1 (not scored): {g1['findings']} findings on {g1['agent_turns_with_g1']} agent turns")
    say("\n--- per call (ALL): hit = strict, +review = needs_review only; units are t<turn><rule> ---")
    for c in a["all"]["per_call"]:
        rev = [u for u in c["hit_with_review"] if u not in c["hit"]]
        fa_r = [u for u in c["false_alarms_with_review"] if u not in c["false_alarms"]]
        tag = "HN" if c["hard_negative"] else ("  " if c["expected"] else "cl")
        say(f"{c['call_id']} {tag} expected [{units(c['expected'])}] hit [{units(c['hit'])}] +review [{units(rev)}] "
            f"MISS [{units(c['missed_with_review'])}] "
            f"FA [{units(c['false_alarms'])}] FA+review [{units(fa_r)}]")
    say(f"stt: {a['stt']['turns']} turns, {a['stt']['requests_made']} requests made, avg {a['stt']['avg_latency_ms']} ms | "
        f"llm: {a['llm']}")


def estimate(scenarios: list[dict], labels_h: str) -> None:
    """Requests and tokens of a full-mode run, from the clean transcripts of a rules_only run (skip applied as in production)."""
    n_agent = n_req = 0
    for sc in scenarios:
        r = load_run("rules_only", "clean", sc["id"], labels_h)
        if not r:
            say(f"no clean rules_only result for {sc['id']}: run the ablation first")
            return
        ctx, hist = assets.context_for(sc), []
        for t in r["turns"]:
            if t["speaker"] == "A":
                n_agent += 1
                fast = fast_findings(ctx, hist, t["idx"], t["text"])
                if t["text"].strip() and not skip.should_skip(ctx, hist, t["text"], fast):
                    n_req += 1
            hist.append(Turn(speaker=t["speaker"], text=t["text"]))
    say(f"agent turns per condition: {n_agent}; language-model requests per condition (after the guarded skip): {n_req}")
    say(f"tokens per condition at {TOKENS_PER_REQUEST} per request: about {n_req * TOKENS_PER_REQUEST:,}")
    say(f"4 conditions (transcripts differ, so no cache sharing; skips may differ a little): about {4 * n_req} requests, "
        f"{4 * n_req * TOKENS_PER_REQUEST:,} tokens. Clean only: {n_req * TOKENS_PER_REQUEST:,}. Clean + 10 dB: {2 * n_req * TOKENS_PER_REQUEST:,}.")


# ---------------------------------------------------------------- main
async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mode", choices=("full", "rules_only"), default="full")
    ap.add_argument("--conditions", default="clean", help="comma list from: " + ",".join(CONDITIONS))
    ap.add_argument("--calls", default="", help="comma list of call ids (default: all 30)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N calls")
    ap.add_argument("--max-tokens", type=int, default=0, help="stop before the language model passes this many tokens in this run")
    ap.add_argument("--report", action="store_true", help="no run: print the report from the results on disk")
    ap.add_argument("--estimate", action="store_true", help="no run: estimate a full-mode run from the clean ablation transcripts")
    ap.add_argument("--rerun", action="store_true", help="ignore existing results for the selected calls (STT and LLM caches still apply)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    scenarios = sorted(assets.scenarios().values(), key=lambda s: s["id"])
    labels_h = es.labels_hash(scenarios)
    conds = [c for c in args.conditions.split(",") if c]
    bad = [c for c in conds if c not in CONDITIONS]
    if bad:
        say(f"unknown condition(s): {bad}")
        return 2
    chosen = [s for s in scenarios if not args.calls or s["id"] in args.calls.split(",")]
    if args.limit:
        chosen = chosen[:args.limit]
    say(f"labels hash {labels_h}; {len(scenarios)} calls, {len(es.label_units(scenarios))} labelled units")

    if args.estimate:
        estimate(scenarios, labels_h)
        return 0
    if not args.report:
        key = settings.gnani_api_key_id
        if not key:
            say("GNANI_API_KEY_ID is not set (environment); cannot transcribe")
            return 2
        if args.mode == "full":
            if not settings.euri_api_key:
                say("EURI_API_KEY is not set (environment); cannot run the language model")
                return 2
            say(f"language model answers cached on disk: {llm.enable_disk_cache(LLM_CACHE)} entries")
        budget = args.max_tokens or None
        stopped = ""
        async with httpx.AsyncClient(timeout=STT_TIMEOUT_S) as stt_client, \
                httpx.AsyncClient(timeout=LLM_TIMEOUT_S, http2=settings.llm_http2) as llm_client:
            clients = {"stt": stt_client, "llm": llm_client}
            try:
                for cond in conds:
                    for sc in chosen:
                        if not args.rerun and load_run(args.mode, cond, sc["id"], labels_h):
                            continue
                        r = await run_call(sc, cond, args.mode, labels_h, clients, key, budget)
                        if r["llm"]["degraded"]:  # a turn without a model answer would silently become rules-only: do not keep it
                            raise Stop(f"{sc['id']}/{cond}: the language model gave no usable answer for {r['llm']['degraded']} turn(s); "
                                       "result not saved")
                        save_run(r)
                        say(f"{args.mode}/{cond}/{sc['id']}: {len(r['detections'])} findings | stt {r['stt']['requests']} new, "
                            f"{r['stt']['cached']} cached | llm {r['llm']}")
            except Stop as e:
                stopped = str(e)
        if stopped:
            say(f"\nSTOPPED CLEANLY: {stopped}. Finished calls are saved; run the same command again to continue.")
        say(f"language model tokens used in this run: {llm.STATS['tokens']} ({llm.STATS['calls']} requests)")
    res = write_results(scenarios, labels_h)
    section = res["full"] if args.mode == "full" else res["ablation_llm_off"]
    for cond in conds:
        if cond in section:
            print_report(section[cond], f"{'LLM-off ablation' if args.mode == 'rules_only' else 'full engine'} / {cond}")
    say(f"\nresults file: {RESULTS.relative_to(ROOT)} (status {res['status']})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
