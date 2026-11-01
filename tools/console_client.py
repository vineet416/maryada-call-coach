"""Throwaway console client: start a session, print the ordered event stream, optionally save it.

  backend/.venv/Scripts/python tools/console_client.py c06 --base http://127.0.0.1:8000 [--mode replay] [--save out.json]
"""
import argparse
import asyncio
import json
import sys
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
    ap.add_argument("--local-keys", action="store_true",
                    help="send the local development keys as visitor keys (what the Settings page does); never printed")
    a = ap.parse_args()
    body: dict = {"scenario_id": a.scenario, "mode": a.mode}
    if a.local_keys:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
        from app.config import settings
        body["credentials"] = {"gnani": {"api_key": settings.gnani_api_key_id},
                               "llm": {"base_url": settings.euri_base_url, "api_key": settings.euri_api_key,
                                       "model": settings.llm_model}}
    async with httpx.AsyncClient() as c:
        r = (await c.post(f"{a.base}/api/sessions", json=body)).json()
    print("session", r)
    events = []
    drops = 0
    while True:  # reconnect by last_seq like the browser does (3 tries)
        try:
            async with websockets.connect(a.base.replace("http", "ws") + r["ws_url"], max_size=None) as ws:
                first = {"type": "resume", "last_seq": events[-1]["seq"]} if events else {"type": "start"}
                await ws.send(json.dumps(first))
                async for raw in ws:
                    e = json.loads(raw)
                    events.append(e)
                    if not a.quiet:
                        print(f"{e['seq']:>3} {e['t_ms']:>6}ms {e['type']:<17} {line(e)}")
            break
        except (websockets.ConnectionClosedError, OSError) as err:
            if events and events[-1]["type"] == "session.ended":
                break  # the server ended the call; a missing close frame afterwards is harmless
            drops += 1
            print(f"connection dropped after seq {events[-1]['seq'] if events else 0}: {type(err).__name__}")
            if drops > 3:
                raise
            await asyncio.sleep(1)
    if drops:
        print("reconnects:", drops)
    if a.save:
        Path(a.save).write_text(json.dumps({"scenario_id": a.scenario, "events": events}, ensure_ascii=False, indent=1),
                                encoding="utf-8")
        print("saved", a.save, len(events), "events")


if __name__ == "__main__":
    asyncio.run(main())
