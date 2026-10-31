# Evaluation notes

Demo with synthetic calls. Not legal advice. Based on RBI/2026-27/223 (effective 1 Jan 2027).

## Known failure examples (kept on purpose)
- **c28, agent turn 3 (held-out call), prefilter only:** the weak R3 phrase "tu sunta hi nahi" matches and produces an R3 `needs_review` finding (confidence 0.6). The label places R3 on turn 5 only, so this counts as one false positive. The phrase list, label, thresholds and weights were not changed, because c28 is in the held-out set and is never tuned against. The LLM check also scored this phrase as R3 in a manual run, so the LLM does not remove it.

Prefilter-only regression on all 30 sample calls (`python tools/prefilter_report.py`): 29 calls match their labels, 1 call (c28) has the false positive above, no misses, no findings on the clean and hard-negative calls.
