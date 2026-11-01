# Evaluation notes

Demo with synthetic calls. Not legal advice. Based on RBI/2026-27/223 (effective 1 Jan 2027).

## Known failure examples (kept on purpose)
- **c28, agent turn 3 (held-out call), prefilter only:** the weak R3 phrase "tu sunta hi nahi" matches and produces an R3 `needs_review` finding (confidence 0.6). The label places R3 on turn 5 only, so this counts as one false positive. The phrase list, label, thresholds and weights were not changed, because c28 is in the held-out set and is never tuned against. The LLM check also scored this phrase as R3 in a manual run, so the LLM does not remove it.

Prefilter-only regression on all 30 sample calls (`python tools/prefilter_report.py`): 29 calls match their labels, 1 call (c28) has the false positive above, no misses, no findings on the clean and hard-negative calls.

## Shorter review prompt: measurement only (not adopted)
Script: `tools/prompt_trim_eval.py`. The candidate prompt lives only in that file and is selected by a script argument; the live prompt in `backend/app/rules/llm.py` is unchanged. Model and settings are the same (`gpt-5.4-mini`, temperature 0, `max_tokens` 250). Context is the new segment plus the previous 2 turns. Token budget for the whole measurement: 35,000 (34,455 used).

Candidate: system prompt 1,531 characters against 2,693 (43% shorter). Rule definitions, the JSON format, the confidence and conservatism guidance and the "copy the quote from the current agent turn in its original script" rule are kept; the four few-shot examples are cut to two (R3 and a clean turn). A first attempt that kept all four examples was only 20% shorter and saved 15% of the tokens, so it was not used for the main comparison.

Hero call c06, 15 agent segments, same transcript for every run (baseline: 2 runs, candidate: 2 runs):

| | Baseline | Candidate |
|---|---|---|
| Prompt tokens per call | 807 | 491 |
| Completion tokens per call | 79 | 75-89 |
| Tokens per hero run | 13,296 | 8,498-8,696 (35% fewer) |
| LLM stage p50 | 1,312 / 1,347 ms | 1,352 / 1,395 ms |
| LLM stage p95 | 1,834 / 1,904 ms | 1,955 / 1,786 ms |
| Valid JSON | 30 of 30 | 29 of 30 |

Latency is unchanged within noise: the saving is in input tokens, and the reply length dominates the wait.

Findings that differ from the baseline (the two baseline runs differ from each other in no finding):
- **Early R3 on turn 7.** The baseline flags the sarcastic first sentence of turn 7 ("Madam, ये सब तो हर कोई बोलता है next week, next week") as R3 with confidence 0.84 and 0.81. The candidate does not flag it in either run. The R3 findings on the later parts of turn 7 (0.98-0.99) and the R5 finding (0.93-0.94 baseline, 0.97 candidate) are present in both.
- **R2 on correct introductions.** The candidate reported R2 on turns where the agent did introduce the company and the recording notice (hero run 1, turns 1 and 3; library call c01, turn 3). The baseline never did.
- **R3 on a mild phrase.** In one candidate run (and in the first attempt), turn 9 ("Sorry madam, आप गलत मत समझिए") is flagged as R3 at 0.88-0.97. The baseline does not flag it.
- **Invalid JSON.** One candidate reply was cut off at `max_tokens` 250 (a long quote in `good_practice`). The baseline reply for the same segment used 244 of the 250 tokens.
- Quotes found verbatim in the original text: 10 of 10 (baseline 12 of 12). No confidence shift above 0.10 on a finding both versions report.

Library calls, one agent turn each, scripted text (no recorded transcript exists for them), alternating baseline and candidate:

| Call, rule | Baseline | Candidate |
|---|---|---|
| c17 turn 5, R4 | R4 0.99 | R4 0.98 |
| c25 turn 5, R6 | no finding | R6 0.98, needs review |
| c22 turn 3, R2 | no finding | no finding |
| c01 turn 3, clean | no finding | R2 0.99 (advisory), a false positive |

Only these four turns fitted in the budget; R1 is not part of the LLM prompt and R5 is covered by the hero call. Each pair is a single sample, and the baseline call of each pair was the first on a fresh connection, so the latency of these pairs is not comparable.

Savings that were estimated from the saved hero runs, not applied: skipping segments under 8 words saves about 19% of the tokens (under 10 words, 25%) and removes no baseline finding. Evaluating once per complete agent turn instead of once per segment (evaluation tools only) uses 6 calls instead of 15 and saves about 59%.
