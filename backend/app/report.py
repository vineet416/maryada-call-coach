"""Call report data: one pure function from a call's event stream (docs/02 events) to everything the report page shows.

It reads only events plus the rulebook and the case meta, so a recorded run and a live call build the same way. Nothing is stored.
"""
from .rules.risk import band

KIND_ORDER = {"violation": 4, "advisory": 3, "needs_review": 2, "good_practice": 1}  # strongest kind wins for a rule's label
NO_REWRITE_RULES = ("R1", "R2")  # nothing to reword: they flag something missing or a time


def _band_edges() -> dict:
    """First score of the medium and the high band, read from the risk module so no threshold is copied here."""
    scores = range(101)
    return {"medium_from": next(s for s in scores if band(s) != "low"), "high_from": next(s for s in scores if band(s) == "high")}


def _final_findings(events: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Latest version of each finding id (an early result is replaced by its deep result), plus when each id first appeared."""
    by_id: dict[str, dict] = {}
    first_ms: dict[str, int] = {}
    for e in events:
        if e["type"] == "finding.detected" and "id" in e["data"]:
            by_id[e["data"]["id"]] = e["data"]
            first_ms.setdefault(e["data"]["id"], e["t_ms"])
    out = sorted(by_id.values(), key=lambda f: (f["turn_idx"], f["token_range"][0], f["id"]))
    return out, first_ms


def _turns(events: list[dict], offsets: dict[int, int]) -> list[dict]:
    """Transcript turns with their tokens, in call order. A repeated turn.started replaces the earlier copy, like the call page."""
    turns: dict[int, dict] = {}
    for e in events:
        d = e["data"]
        if e["type"] == "turn.started":
            turns[d["turn_idx"]] = {"idx": d["turn_idx"], "speaker": d["speaker"], "offset_ms": offsets.get(d["turn_idx"], 0),
                                    "duration_ms": d.get("duration_ms", 0), "tokens": []}
        elif e["type"] == "transcript.final" and d["turn_idx"] in turns:
            have = {t["i"] for t in turns[d["turn_idx"]]["tokens"]}
            if d.get("tokens") and d["tokens"][0]["i"] in have:
                continue  # the same segment again after a resume
            turns[d["turn_idx"]]["tokens"] += d.get("tokens", [])
    for t in turns.values():
        t["tokens"].sort(key=lambda x: x["i"])
    return [turns[k] for k in sorted(turns)]


def _rewrite(f: dict) -> str | None:
    """The suggested rewording, or None when there is none to show (R1, R2 and fast-check-only findings never have one)."""
    text = (f.get("rewrite") or "").strip()
    if not text or f["rule_id"] in NO_REWRITE_RULES or f.get("source") == "prefilter":
        return None
    return text


def build_report(events: list[dict], meta: dict, rules: list[dict], source: str) -> dict:
    """`meta`: id, title, date, time, duration_ms, turn_offsets {idx: ms}. `rules`: rulebook entries (id, title, why).
    `source`: "replay" or "live"."""
    title = {r["id"]: r["title"] for r in rules}
    why = {r["id"]: (r.get("why") or "").strip() for r in rules}
    findings, first_ms = _final_findings(events)
    flagged = [f for f in findings if f["kind"] != "good_practice"]
    good = [f for f in findings if f["kind"] == "good_practice"]
    nudge = {e["data"]["finding_id"]: e["data"]["text"] for e in events if e["type"] == "coach.nudge" and e["data"].get("finding_id")}

    risk = [{"t_ms": e["t_ms"], "score": e["data"]["score"], "band": e["data"]["band"], "delta": e["data"].get("delta", 0),
             "reason_rule_id": e["data"].get("reason_rule_id")} for e in events if e["type"] == "risk.update"]
    peak = max(risk, key=lambda r: r["score"], default=None)
    flag_times = [first_ms[f["id"]] for f in flagged]

    by_rule: dict[str, dict] = {}
    for f in flagged:
        row = by_rule.setdefault(f["rule_id"], {"rule_id": f["rule_id"], "title": title.get(f["rule_id"], f["rule_id"]), "count": 0, "kind": f["kind"]})
        row["count"] += 1
        if KIND_ORDER[f["kind"]] > KIND_ORDER[row["kind"]]:
            row["kind"] = f["kind"]

    return {
        "scenario": {"id": meta["id"], "title": meta["title"], "call_date": meta.get("date"), "call_time": meta.get("time"),
                     "duration_ms": meta.get("duration_ms")},
        "source": source,
        "bands": _band_edges(),
        "kpis": {"peak_risk": peak["score"] if peak else 0, "peak_band": peak["band"] if peak else band(0),
                 "findings_count": len(flagged), "good_count": len(good), "first_flag_ms": min(flag_times) if flag_times else None},
        "risk": risk,
        "flags": sorted(({"finding_id": f["id"], "rule_id": f["rule_id"], "kind": f["kind"], "turn_idx": f["turn_idx"], "t_ms": first_ms[f["id"]]}
                         for f in flagged), key=lambda x: x["t_ms"]),
        "by_rule": sorted(by_rule.values(), key=lambda r: (-r["count"], r["rule_id"])),
        "turns": _turns(events, meta.get("turn_offsets", {})),
        "findings": findings,
        "coaching": [{"finding": f, "rule_title": title.get(f["rule_id"], f["rule_id"]), "why": why.get(f["rule_id"]) or None,
                      "coach_line": nudge.get(f["id"]), "rewrite": _rewrite(f)} for f in flagged],
        "good": [{"finding": f, "t_ms": first_ms[f["id"]]} for f in good],
    }
