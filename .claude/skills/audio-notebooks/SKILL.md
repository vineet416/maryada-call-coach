---
name: audio-notebooks
description: Working on notebooks/ and tools/audio_lib.py (TTS, phone chain, noise, gates G1/G2). Use for any audio generation task.
---
# Audio notebooks (full spec: docs/11)
- Edit only `notebooks/*.py` (jupytext percent). Never read `.ipynb` or audio. Run headless as scripts; then `jupytext --sync notebooks/*.py`. `nbstripout` must be active.
- Order: 01 audition (gate G1, user listens) -> 02 generate hero (gate G2) -> 02 all calls -> 03 noise -> 04 video assets. At each gate STOP and wait for the user's answer; never use the defaults in `content/voices.yaml` unasked (they are only the recommendation shown at the gate).
- TTS: model `timbre-v3.0`; text <= 600 chars, split on sentence boundaries; cache by hash in `data/audio/_cache/` so reruns are free; budget about Rs 80 for everything.
- Voices from `content/voices.yaml`: c06 uses the `hero` block only (Prakash, Shivani, Avinash, Shubham, vo Shubham wideband); the other calls use `library_pool` with its rules (no shared voice inside a call, gender from the script, Shubham only as coach, Lakshmi only after the user approves a V2 sample). No audio tags; an agent line that carries a violation label is raised +3.5 dB (-18.5 LUFS), level only.
- Chain: TTS -> loudnorm (agent -22, borrower -24, third -25 LUFS) -> 8 kHz band-pass 300-3400 Hz + compressor -> gaps 350-700 ms (seed 42). Coach and VO stay full-band (coach -26, VO -16 LUFS).
- Dialogue comes only from `content/`; edit it only to fix TTS spelling, and log it.
