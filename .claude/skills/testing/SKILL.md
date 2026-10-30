---
name: testing
description: Maryada testing strategy and how to write tests. Use when adding tests, deciding what to test, or checking a change.
---
# Testing
- **Test only pure functions** with pytest: `align`, `risk`, `engine` thresholds/merge, R1/R2/R4 gates, `manager/aggregate`, `url_guard`, `redact`. Location: `backend/tests/test_<module>.py`.
- No HTTP-mock suites, no live-API tests, no snapshot tests. Network behaviour is verified manually (hero call, replay, bad key, cap).
- Style: `@pytest.mark.parametrize` tables; one behaviour per test; name `test_<behaviour>`; no shared mutable fixtures.
- Must-have cases: thresholds (0.75 / 0.45), once-per-rule-per-turn risk, risk bands (30 / 60), R1 08:00-19:00 edges, R2 look-back, Devanagari+Roman quote alignment, SSRF URL rejections, key redaction.
- The hero call c06 is the golden case: expected labels live in `content/scenarios/02_r3_abuse_threats.yaml`; assert the engine reproduces them from the prefilter alone.
- Run `/test` after finishing a unit of work, not after every edit. Failing test: fix the code, never weaken the assertion unless the spec changed (then log it in docs/DECISIONS.md).
- Evaluation (`tools/run_eval.py`) is a measurement, not a unit test: tune on the tune split only (content/split.yaml).
