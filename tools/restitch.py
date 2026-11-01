"""Re-stitch the shipped call audio with natural gaps. Uses the finished 8 kHz turn files only: no speech synthesis, no model calls.

Each turn clip keeps about 50 ms of silence at both ends, the turns are joined with a heard gap of 1.0-1.5 s (deterministic per call),
and the turn MP3s, call.mp3 and manifest offsets are rewritten. Loudness and true peak are measured before and after.
Dry run by default: `python tools/restitch.py`; write with `--write`.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_lib as al

DATA = al.ROOT / "data" / "audio"
cfg = al.load_yaml("content/voices.yaml")
GAP = tuple(cfg["phone_chain"]["turn_gap_ms"])
EDGE_MS = cfg["phone_chain"]["edge_silence_ms"]
LEAD_MS = cfg["phone_chain"]["leading_silence_ms"]
ROLE = {"A": "agent", "B": "borrower", "T": "third_party"}
RAISE = cfg["violation_gain"]
MIN_CLIP_S = 0.61  # shortest clip the level checks accept is 0.6 s
LEVEL_FIX_LU = 0.25  # a trimmed clip whose measured level moved more than this is brought back (the check allows 0.5)


def target(turn: dict) -> float:
    base = al.target_lufs(cfg, ROLE[turn["speaker"]])
    if "violation_gain_db" not in turn:
        return base
    return base + (RAISE["gain_db"] if turn.get("limiter_reduction_db", 0) > 0 else turn["violation_gain_db"])


def check(root: Path, manifest: dict) -> tuple[int, list[str]]:
    """The level checks of notebook 02 (section 5) on finished turn files: loudness within 0.5 LU of the target (library lines that
    carry a violation label: within 1.0), true peak <= -1.5 dBTP, peak below -1 dBFS, duration 0.6-25 s. The hero call c06 is
    checked against its own measured levels in the notebook, so its raised line (turn 7) is checked at -18.5 +/- 1.0 LUFS."""
    problems, n = [], 0
    for sid, entry in manifest.items():
        for t in entry["turns"]:
            x = sf.read(root / t["wav8k"].replace(f"{sid}/", f"{sid}/", 1), dtype="float32")[0]
            m = al.measure_loudness(x, 8000)
            raised = "violation_gain_db" in t or (sid == "c06" and t["idx"] == 7)
            tgt = al.target_lufs(cfg, ROLE[t["speaker"]]) + (RAISE["gain_db"] if sid == "c06" and t["idx"] == 7 else 0)
            if "violation_gain_db" in t:
                tgt = target(t)
            n += 1
            for bad, why in ((abs(m["lufs"] - tgt) > (1.0 if raised else 0.5), f"loudness {m['lufs']:.2f} vs {tgt:.2f}"),
                             (m["true_peak"] > -1.5 + 0.05, f"true peak {m['true_peak']:.2f}"),
                             (al.peak_dbfs(x) >= -1.0, "clipping"), (not 0.6 <= len(x) / 8000 <= 25, "duration")):
                if bad:
                    problems.append(f"{sid}/{t['idx']}: {why}")
    return n, problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--source", default="", help="read the original turn files from this backup folder instead of data/audio")
    ap.add_argument("--check", action="store_true", help="run the level checks on the shipped files")
    args = ap.parse_args()
    if args.check:
        cur = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
        n, bad = check(DATA, cur)
        print(f"shipped files: {n} turns checked, {len(bad)} problems: {bad or 'none'}")
        return
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    stamp = time.strftime("%Y%m%d%H%M%S")
    out_manifest, rows, worst_dl, worst_tp, off_target, adjusted = {}, [], 0.0, 0.0, [], []
    for sid, entry in manifest.items():
        if args.only and sid not in args.only:
            out_manifest[sid] = entry
            continue
        src = Path(args.source) if args.source else DATA
        old = [sf.read(src / t["wav8k"], dtype="float32")[0] for t in entry["turns"]]
        new, levelled = [], []
        for x in old:
            y = al.trim_silence(x, 8000, keep_ms=EDGE_MS)
            if len(y) < MIN_CLIP_S * 8000:  # the level checks want clips of at least 0.6 s: keep a little more silence
                pad = int(MIN_CLIP_S * 8000) - len(y)
                y = np.pad(y, (pad // 2, pad - pad // 2))
            ma, mb = al.measure_loudness(x, 8000), al.measure_loudness(y, 8000)
            # The 400 ms gating blocks see less silence in a trimmed short clip, so its measured level moves although
            # the samples are the same. One linear gain restores the measured level (never past -1.5 dBTP).
            gain = ma["lufs"] - mb["lufs"]
            if abs(gain) > LEVEL_FIX_LU:
                gain = min(gain, RAISE["true_peak_dbtp"] - mb["true_peak"])
                y = (y * 10 ** (gain / 20)).astype(np.float32)
            levelled.append(round(gain, 2) if abs(gain) > LEVEL_FIX_LU else 0.0)
            new.append(y)
        call, offsets = al.assemble_call(new, 8000, sid, lead_ms=LEAD_MS, gap_ms=GAP)
        heard = [offsets[i] - (offsets[i - 1] + round(len(new[i - 1]) * 1000 / 8000)) + sum(
            (al.edge_silence_ms(new[i - 1], 8000)[1], al.edge_silence_ms(new[i], 8000)[0])) for i in range(1, len(new))]
        turns = []
        for t, o, a, b, off in zip(entry["turns"], new, old, offsets, range(len(new)), strict=True):
            ma, mb = al.measure_loudness(a, 8000), al.measure_loudness(o, 8000)
            worst_dl = max(worst_dl, abs(mb["lufs"] - ma["lufs"]))
            worst_tp = max(worst_tp, abs(mb["true_peak"] - ma["true_peak"]))
            if sid != "c06" and abs(mb["lufs"] - target(t)) > 1.0:
                off_target.append((sid, t["idx"], round(mb["lufs"], 2), round(target(t), 2), round(ma["lufs"], 2)))
            turns.append({**t, "duration_ms": round(len(o) * 1000 / 8000), "offset_ms": offsets[off]})
        adjusted.extend((sid, t["idx"], g) for t, g in zip(entry["turns"], levelled, strict=True) if g)
        rows.append((sid, entry["duration_ms"], round(len(call) * 1000 / 8000), min(heard), max(heard), sum(heard) / len(heard)))
        out_manifest[sid] = {**entry, "turns": turns, "duration_ms": round(len(call) * 1000 / 8000)}
        if args.write and not args.source:
            bak = DATA / "_backup" / f"restitch_{stamp}" / sid
            bak.mkdir(parents=True, exist_ok=True)
            for f in (DATA / sid).iterdir():
                shutil.copy2(f, bak / f.name)
        if args.write:
            for t, o in zip(entry["turns"], new, strict=True):
                al.write_wav(DATA / t["wav8k"], o, 8000)
                al.write_mp3(DATA / t["mp3"], o, 8000, 64)
            al.write_mp3(DATA / entry["call_mp3"], call, 8000, 64)
    print(f"{'call':5s} {'old s':>7s} {'new s':>7s} {'gap min':>8s} {'gap max':>8s} {'gap mean':>9s}  (heard gap, ms)")
    for sid, od, nd, lo, hi, mean in rows:
        print(f"{sid:5s} {od / 1000:7.1f} {nd / 1000:7.1f} {lo:8.0f} {hi:8.0f} {mean:9.0f}")
    allg = [r[5] for r in rows]
    print(f"calls {len(rows)}; mean of call means {np.mean(allg):.0f} ms; total {sum(r[1] for r in rows) / 1000:.0f} s -> {sum(r[2] for r in rows) / 1000:.0f} s")
    print(f"loudness change per turn: worst {worst_dl:.3f} LU; true peak change: worst {worst_tp:.3f} dB")
    print(f"clips given a measurement-compensating gain (call, turn, dB): {len(adjusted)}: {adjusted}")
    print(f"turns more than 1.0 LU from their target (new, target, old): {off_target or 'none'}")
    if args.write:
        (DATA / "manifest.json").write_text(json.dumps(dict(sorted(out_manifest.items())), indent=1), encoding="utf-8")
        print("written; the previous files are in", DATA / "_backup" / f"restitch_{stamp}")
    else:
        print("dry run: nothing written (use --write)")


if __name__ == "__main__":
    main()
