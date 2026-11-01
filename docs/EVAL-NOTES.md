# Evaluation notes

Demo with synthetic calls. Not legal advice. Based on RBI/2026-27/223 (effective 1 Jan 2027).

## Known failure examples (kept on purpose)
- **c28, agent turn 3 (held-out call), prefilter only:** the weak R3 phrase "tu sunta hi nahi" matches and produces an R3 `needs_review` finding (confidence 0.6). The label places R3 on turn 5 only, so this counts as one false positive. The phrase list, label, thresholds and weights were not changed, because c28 is in the held-out set and is never tuned against. The LLM check also scored this phrase as R3 in a manual run, so the LLM does not remove it.

Prefilter-only regression on all 30 sample calls (`python tools/prefilter_report.py`): 29 calls match their labels, 1 call (c28) has the false positive above, no misses, no findings on the clean and hard-negative calls.

## Shorter review prompt: measurement only (not adopted)
Script: `tools/prompt_trim_eval.py`. The candidate prompt lives only in that file and is selected by a script argument; the live prompt in `backend/app/rules/llm.py` is unchanged. Model and settings are the same (`gpt-5.4-mini`, temperature 0, `max_tokens` 250). Context is the new segment plus the previous 2 turns. Token budget for the whole measurement: 35,000. The new calls used 34,455 (the first attempt, two candidate hero runs and the four library pairs); the two baseline hero runs were reused from an earlier model comparison with the same prompt and settings, and were not run again.

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
- **R2 on correct introductions.** The candidate reported R2 on turns where the agent did introduce the company and the recording notice (hero run 1, turns 1 and 3; library call c01, turn 3). The baseline never did. Resolved: R2 is now rule-based only, judged on the completed second agent turn, with script-tolerant matching (see DECISIONS, 2026-11-01); hero risk path is 0, 0, 0, 65, 55, 45.
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

## Short-segment skip and result cache

The production prompt is unchanged. Two token savers were added to the live pipeline.

**Guarded skip.** The language-model review is skipped for agent text of fewer than 8 words (setting `SKIP_LLM_MAX_WORDS`) only when the fast prefilter and the gates found nothing and the text holds no abuse, threat, legal, third-party or sensitive-occasion phrase from the rule lists (also not when the call has a sensitive occasion in its context). A skipped review is counted as skipped, not as a clean result. `tools/short_segment_audit.py` (no model calls) lists every agent text unit under a word limit in the 30 calls: 101 units under 8 words (whole turns and sentence prefixes), 73 of which would be skipped. Every unit that contains a labelled phrase has 6 words or fewer and is either flagged by the prefilter or carries a keyword, so none is skipped; no limit from 5 to 16 words would skip one on this data. The only short whole turns with a label are the R1 gate findings, which do not use the model. The hero call has 15 agent segments, 3 of them under 8 words (6, 6 and 7), none labelled.

**Cache.** Valid model replies are cached in memory by model, endpoint and prompt hash, for the server's own key only. Hero call, model stage only, two runs in one process (`tools/llm_cache_check.py`): run 1 used 12 requests and 10,849 tokens (3 segments skipped, 904 tokens per request); run 2 used 0 requests and 0 tokens (12 cache hits) with identical findings. Findings against the earlier baseline: turn 7 early R3 flag 0.84 (segment 1), R3 0.99-1.0 later, R5 0.95-0.97 kept, no new findings on the clean turns (the only extra items are the rule-based good-practice and R2 advisory items that the recorded replay also contains).

**Cost of a full evaluation run (estimate, not measured).** 30 calls x 4 noise conditions, one request per complete agent turn: 165 agent turns per condition, 20 of them skippable, so 145 requests per condition and 580 per run, about 520,000-580,000 tokens at 900-1,000 tokens per request. The cache does not help across conditions (the transcripts differ), but repeated runs with an unchanged prompt and model, such as rule-threshold or report changes, cost 0. The model-off ablation costs nothing.
