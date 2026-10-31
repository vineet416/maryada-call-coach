"""Throwaway console client: start a session, print the ordered event stream, optionally save it.

  backend/.venv/Scripts/python tools/console_client.py c06 --base http://127.0.0.1:8000 [--mode replay] [--save out.json]
"""
import argparse
import asyncio
import json
from pathlib import Path

import httpx2 as httpx
import websockets


def line(e: dict) -> str:
    d, t = e["data"], e["type"]
    if t == "transcript.final":
        return f"turn {d['turn_idx']} seg {d['segment_idx']} {d['speaker']}: {d['text'][:90]}"
    if t == "finding.detected":
        return f"{d['phase']} {d['rule_id']} {d['kind']} conf={d['confidence']:.2f} src={d['source']} tok={d['token_range']} total={d['latency']['total_ms']}ms quote={d['quote'][:50]!r}"
    if t == "coach.nudge":
        return f"{d['rule_id']} {d['text']}"
    if t == "risk.update":
        return f"score={d['score']} delta={d['delta']} band={d['band']} reason={d['reason_rule_id']}"
    return json.dumps(d, ensure_ascii=False)[:100]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--mode", default="live")
    ap.add_argument("--save")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    async with httpx.AsyncClient() as c:
        r = (await c.post(f"{a.base}/api/sessions", json={"scenario_id": a.scenario, "mode": a.mode})).json()
    print("session", r)
    events = []
    async with websockets.connect(a.base.replace("http", "ws") + r["ws_url"], max_size=None) as ws:
        await ws.send(json.dumps({"type": "start"}))
        async for raw in ws:
            e = json.loads(raw)
            events.append(e)
            if not a.quiet:
                print(f"{e['seq']:>3} {e['t_ms']:>6}ms {e['type']:<17} {line(e)}")
    if a.save:
        Path(a.save).write_text(json.dumps({"scenario_id": a.scenario, "events": events}, ensure_ascii=False, indent=1),
                                encoding="utf-8")
        print("saved", a.save, len(events), "events")


if __name__ == "__main__":
    asyncio.run(main())
