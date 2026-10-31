---
name: audio-notebooks
description: Working on notebooks/ and tools/audio_lib.py (TTS, phone chain, noise, gates G1/G2). Use for any audio generation task.
---
# Audio notebooks (full spec: docs/11)
- Edit only `notebooks/*.py` (jupytext percent). Never read `.ipynb` or audio. Run headless as scripts; then `jupytext --sync notebooks/*.py`. `nbstripout` must be active.
- Order: 01 audition (gate G1, user listens) -> 02 generate hero (gate G2) -> 02 all calls -> 03 noise -> 04 video assets. At each gate STOP and wait for the user's answer; never use the defaults in `content/voices.yaml` unasked (they are only the recommendation shown at the gate).
- TTS: model `timbre-v3.0`; text <= 600 chars, split on sentence boundaries; cache by hash in `data/audio/_cache/` so reruns are free; budget about Rs 80 for everything.
- Voice per role from `content/voices.yaml`: ONE voice per role for the whole MVP (agent Prakash, borrower Shivani, third party Avinash, coach Shubham, vo Shubham wideband); no alternates, no per-call variation. The only audio tag is `<shouting>` at the start of the c06 threat line (+2.5 dB).
- Chain: TTS -> loudnorm (agent -22, borrower -24, third -25 LUFS) -> 8 kHz band-pass 300-3400 Hz + compressor -> gaps 350-700 ms (seed 42). Coach and VO stay full-band (coach -26, VO -16 LUFS).
- Dialogue comes only from `content/`; edit it only to fix TTS spelling, and log it.
