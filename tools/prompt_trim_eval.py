"""Measure a shortened LLM review prompt against the current one (LLM stage only; the live pipeline is not touched).

Run with the backend interpreter (it imports the app settings and rule engine):

  backend/.venv/Scripts/python.exe tools/prompt_trim_eval.py run VARIANT TAG [--call c06] [--turns 3,5] --out DIR
  backend/.venv/Scripts/python.exe tools/prompt_trim_eval.py pair TAG --call c17 --turns 5,7 --out DIR
  backend/.venv/Scripts/python.exe tools/prompt_trim_eval.py report --base FILE [--base FILE] --cand FILE [--cand FILE]

VARIANT is `baseline` (the current prompt from app.rules.llm), `candidate` (about half the size, defined below) or
`candidate_v1` (a first, only ~20% shorter attempt). The variant can also be
set with the PROMPT_VARIANT environment variable. `c06` uses the recorded replay transcript (one call per agent segment,
cumulative text, as the live pipeline sends it). Other calls use the scripted agent turns, one call per turn.
`pair` alternates baseline and candidate turn by turn so both see the same network conditions.

All token use reported by the API is added to DIR/ledger.json (a failed call without usage adds nothing); every call is refused once the total would pass TOKEN_BUDGET.
Failed calls are recorded and never retried. The API key is read through the app settings and never printed.
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings
from app.rules import llm
from app.rules.engine import kind_for, llm_to_findings, parse_llm
from app.rules.loader import load_rules
from app.rules.schemas import Turn
from app.session import assets

TOKEN_BUDGET = 35_000
EST_NEXT_CALL = 1000  # refuse a call when the ledger plus this estimate would pass the budget (a call costs up to ~900)

CANDIDATE_FEW_SHOT = """Examples:
A: "Sir, EMI do din se pending hai. Kya link bhej doon?"
{"findings":[],"good_practice":[{"quote":"Kya link bhej doon","note":"Clear, polite way to pay."}]}
A: "Padosiyon ko pata chalega to samajh aayega."
{"findings":[{"rule_id":"R3","confidence":0.95,"quote":"Padosiyon ko pata chalega","reason":"Threatens public shaming.","rewrite":"Kab tak payment possible hoga?","kind":"violation"}],"good_practice":[]}
A: "Kal police ghar pahunch jayegi."
{"findings":[{"rule_id":"R5","confidence":0.92,"quote":"police ghar pahunch jayegi","reason":"Invents police action.","rewrite":"Pehle koi option dekhte hain.","kind":"violation"}],"good_practice":[]}
(answered_by: spouse) A: "Unki EMI pending hai, 18000 baaki hain."
{"findings":[{"rule_id":"R4","confidence":0.95,"quote":"Unki EMI pending hai, 18000 baaki hain","reason":"Reveals loan and amount to a third party.","rewrite":"Kya unse baat ho sakti hai?","kind":"violation"}],"good_practice":[]}"""


def candidate_v1_system_prompt() -> str:
    lines = [f"{r['id']} {r['title']}: {r['summary']}" for r in load_rules()["rules"] if r["id"] not in ("R1", "G1")]
    return (
        "Compliance reviewer for Indian loan-recovery calls (Hindi, English, Hinglish; Roman or Devanagari; synthetic).\n"
        "Rules (R1 is checked elsewhere):\n" + "\n".join(lines) + "\n"
        "Flag only clear breaches. Firm-but-polite dues reminders, true statements about late fees, credit score "
        "or a notice allowed by the agreement are NOT violations. R4 only when answered_by is not the borrower.\n"
        'Reply JSON only: {"findings":[{"rule_id","confidence","quote","reason","rewrite","kind"}],'
        '"good_practice":[{"quote","note"}]}. "quote": copied verbatim from the CURRENT agent turn, in its original '
        'script. "reason": English, max 160 characters. "rewrite": polite Hinglish, same register. '
        "Empty findings is valid.\n" + CANDIDATE_FEW_SHOT
    )


def candidate_system_prompt() -> str:
    """About half the size of the current system prompt: rule definitions, guidance, JSON format and the
    quote rule kept; two short examples instead of four."""
    lines = [f"{r['id']} {r['title']}: {r['summary']}" for r in load_rules()["rules"] if r["id"] not in ("R1", "G1")]
    return (
        "Compliance reviewer for Indian loan-recovery calls (Hindi, English, Hinglish, any script; synthetic).\n"
        "Rules (R1 is checked elsewhere):\n" + "\n".join(lines) + "\n"
        "Flag clear breaches only. Firm polite dues reminders, true statements about late fees or credit score, and "
        "notices allowed by the agreement are fine. R4 only when answered_by is not the borrower.\n"
        'JSON only: {"findings":[{"rule_id","confidence","quote","reason","rewrite","kind"}],'
        '"good_practice":[{"quote","note"}]}. quote: copied verbatim from the CURRENT agent turn, in its original '
        "script. reason: English, max 160 chars. rewrite: polite Hinglish, same register. Empty findings is valid.\n"
        'A: "Padosiyon ko pata chalega to samajh aayega."\n'
        '{"findings":[{"rule_id":"R3","confidence":0.95,"quote":"Padosiyon ko pata chalega","reason":"Public shaming '
        'threat.","rewrite":"Kab tak payment possible hoga?","kind":"violation"}],"good_practice":[]}\n'
        'A: "Kya link bhej doon?"\n'
        '{"findings":[],"good_practice":[{"quote":"Kya link bhej doon","note":"Polite way to pay."}]}'
    )



PROMPTS = {"baseline": llm.system_prompt, "candidate_v1": candidate_v1_system_prompt,
           "candidate": candidate_system_prompt}


def ledger_path(out: Path) -> Path:
    return out / "ledger.json"


def ledger_total(out: Path) -> int:
    p = ledger_path(out)
    return json.loads(p.read_text())["total"] if p.exists() else 0


def ledger_add(out: Path, n: int) -> int:
    total = ledger_total(out) + n
    ledger_path(out).write_text(json.dumps({"total": total, "budget": TOKEN_BUDGET}))
    return total


def hero_calls():
    """(turn_idx, history[-2:], cumulative text) for every agent segment of c06 with >= MIN_WORDS words."""
    ev = json.loads((ROOT / "data/replay/c06.json").read_text(encoding="utf-8"))["events"]
    segs = [e["data"] for e in ev if e["type"] == "transcript.final"]
    spk = {t["idx"]: t["speaker"] for t in assets.audio_manifest()["c06"]["turns"]}
    history, calls = [], []
    for idx in sorted({s["turn_idx"] for s in segs}):
        text = ""
        for s in (s for s in segs if s["turn_idx"] == idx):
            text = f"{text} {s['text']}".strip()
            if spk[idx] == "A" and len(text.split()) >= llm.MIN_WORDS:
                calls.append((idx, list(history[-2:]), text))
        history.append(Turn(speaker=spk[idx], text=text))
    return calls


def scripted_calls(cid: str, only: set[int] | None):
    turns = assets.scenarios()[cid]["turns"]
    history, calls = [], []
    for n, t in enumerate(turns, 1):
        if t["s"] == "A" and len(t["t"].split()) >= llm.MIN_WORDS and (only is None or n in only):
            calls.append((n, list(history[-2:]), t["t"]))
        history.append(Turn(speaker=t["s"], text=t["t"]))
    return calls


async def one_call(client, variant, ctx, history, text, out):
    if ledger_total(out) + EST_NEXT_CALL > TOKEN_BUDGET:
        return {"error": "budget_stop"}
    body = {"model": settings.llm_model, "temperature": 0, "max_tokens": 250,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": PROMPTS[variant]()},
                         {"role": "user", "content": llm.user_prompt(ctx, history, text)}]}
    url = settings.euri_base_url.rstrip("/") + "/chat/completions"
    t0 = time.perf_counter()
    try:
        r = await client.post(url, json=body, headers={"Authorization": f"Bearer {settings.euri_api_key}"})
        ms = int((time.perf_counter() - t0) * 1000)
    except Exception as e:  # noqa: BLE001 - recorded, never retried
        return {"error": type(e).__name__, "ms": int((time.perf_counter() - t0) * 1000)}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "body": r.text[:200], "ms": ms}
    j = r.json()
    u = j.get("usage") or {}
    ledger_add(out, u.get("total_tokens") or 0)
    return {"ms": ms, "usage": u, "finish": j["choices"][0].get("finish_reason"),
            "raw": j["choices"][0]["message"]["content"]}


def decorate(row, idx, text):
    if "raw" not in row:
        return row
    parsed = parse_llm(row["raw"])
    row["valid"] = parsed is not None
    if parsed:
        row["findings"] = [{"rule": f.rule_id, "conf": f.confidence, "quote": f.quote,
                            "kind": kind_for(f.rule_id, f.confidence), "weak": f.weak_alignment}
                           for f in llm_to_findings(parsed, idx, text)]
        row["quotes_raw"] = [f.quote for f in parsed.findings]
        row["good"] = [g.quote for g in parsed.good_practice]
    return row


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "pair", "report"])
    ap.add_argument("pos", nargs="*")
    ap.add_argument("--call", default="c06")
    ap.add_argument("--turns", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--base", action="append", default=[])
    ap.add_argument("--cand", action="append", default=[])
    a = ap.parse_args()
    if a.cmd == "report":
        return report(a.base, a.cand)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = {int(x) for x in a.turns.split(",") if x} or None
    sc = assets.scenarios()[a.call]
    ctx = assets.context_for(sc)
    if a.call == "c06":
        calls = [c for c in hero_calls() if only is None or c[0] in only]
    else:
        calls = scripted_calls(a.call, only)
    variants = ["baseline", "candidate"] if a.cmd == "pair" else [a.pos[0] if len(a.pos) > 1 else os.environ.get("PROMPT_VARIANT", "baseline")]
    tag = a.pos[-1]
    rows = {v: [] for v in variants}
    async with llm.make_client() as client:
        for idx, hist, text in calls:  # variants alternate within each turn
            for v in variants:
                res = await one_call(client, v, ctx, hist, text, out)
                rows[v].append(decorate({"turn": idx, "text": text, **res}, idx, text))
                print(f"  {a.call} t{idx} {v}: {res.get('ms', '-')} ms  ledger {ledger_total(out)}/{TOKEN_BUDGET}", flush=True)
    for v in variants:
        f = out / f"{tag}_{a.call}_{v}.json"
        f.write_text(json.dumps(rows[v], ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{f.name}: {len(rows[v])} calls, errors={sum('error' in r for r in rows[v])}")
    print(f"RUNNING TOTAL: {ledger_total(out)} / {TOKEN_BUDGET} tokens")


def load(files):
    rows = []
    for f in files:
        rows += json.loads(Path(f).read_text(encoding="utf-8"))
    return rows


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))] if xs else None


def stats(rows, label):
    ok = [r for r in rows if "usage" in r]
    ms = [r["ms"] for r in ok]
    print(f"{label}: calls {len(rows)}, ok {len(ok)}, valid JSON {sum(r.get('valid', False) for r in ok)}/{len(ok)}")
    if ok:
        pt = statistics.mean(r["usage"]["prompt_tokens"] for r in ok)
        ct = statistics.mean(r["usage"]["completion_tokens"] for r in ok)
        print(f"  tokens/call prompt {pt:.0f} completion {ct:.0f} total {pt + ct:.0f}; per 15 calls {15 * (pt + ct):.0f}")
        print(f"  latency p50 {pct(ms, 50)} ms, p95 {pct(ms, 95)} ms, max {max(ms)} ms")
        q = [(f["quote"] in r["text"]) for r in ok for f in r.get("findings", [])]
        print(f"  quote found verbatim in original turn: {sum(q)}/{len(q)}")


def fmt(r):
    if "findings" not in r:
        return "ERR"
    return ",".join(f"{f['rule']} {f['conf']:.2f}" for f in r["findings"]) or "-"


def diff(ref, new, label):
    """Differences of one run against a reference run, paired by call position."""
    n = 0
    for i, (o, r) in enumerate(zip(ref, new)):
        if "findings" not in o or "findings" not in r:
            continue
        of, nf = {f["rule"]: f for f in o["findings"]}, {f["rule"]: f for f in r["findings"]}
        for rule in sorted(set(of) | set(nf)):
            x, y = of.get(rule), nf.get(rule)
            if x and not y:
                msg = f"MISSED {rule} (ref {x['conf']:.2f})"
            elif y and not x:
                msg = f"NEW {rule} ({y['conf']:.2f}): {y['quote'][:40]}"
            elif abs(x["conf"] - y["conf"]) > 0.10 or x["kind"] != y["kind"]:
                msg = f"SHIFT {rule} {x['conf']:.2f}->{y['conf']:.2f} ({x['kind']}->{y['kind']})"
            else:
                continue
            n += 1
            print(f"  [{label}] call {i + 1} (turn {r['turn']}): {msg}")
    print(f"  [{label}] {n} difference(s)")


def report(base, cand):
    """--base files: one per baseline run; --cand files: one per candidate run (each file = one run, same calls)."""
    B, C = [load([f]) for f in base], [load([f]) for f in cand]
    for k, rows in enumerate(B):
        stats(rows, f"BASELINE run {k + 1}")
    for k, rows in enumerate(C):
        stats(rows, f"CANDIDATE run {k + 1}")
    print()
    print("Findings per call (turn: base1 | base2 | cand1 | cand2):")
    for i in range(len(B[0])):
        cols = [fmt(run[i]) if i < len(run) else "n/a" for run in B + C]
        print(f"  {i + 1:>2} t{B[0][i]['turn']:<2} " + " | ".join(cols))
    if len(B) > 1:
        print()
        print("Noise floor (baseline run 2 vs run 1):")
        diff(B[0], B[1], "base2-vs-base1")
    for k, rows in enumerate(C):
        print()
        print(f"Candidate run {k + 1} vs baseline run 1:")
        diff(B[0], rows, f"cand{k + 1}")


if __name__ == "__main__":
    asyncio.run(main())
