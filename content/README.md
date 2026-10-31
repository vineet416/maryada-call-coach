# content/ — the script pack (source of truth for all call content)

Authored in advance so no dialogue has to be invented during the build. It may be edited only to fix typos or TTS-unfriendly spellings; log any change in the decision log.

## Files
- `agents.yaml` — 8 fictional agents (profile, gender, team). All agents speak with the single agent voice; `voice_role` is a legacy hint that the audio notebooks ignore.
- `voices.yaml` — the final single-voice casting (agent Prakash, borrower Shivani, third party Avinash, coach Shubham, voice-over Shubham), tag rule, TTS parameters, loudness targets (docs/11).
- `audition.yaml` — the short clips for the first listening test (notebook 01).
- `rules_phrases.yaml` — phrase lists (Roman + Devanagari), coach lines, praise lines per rule.
- `split.yaml` — which calls are the tune set vs the held-out set for evaluation.
- `scenarios/*.yaml` — the 30 calls (c01–c30). Hero call = `c06`.

## Scenario schema (compact; overrides docs/04 §2)
Each file has `scenarios:` (a list). Per scenario: `id, title, summary, agent (agents.yaml id), date, time (IST, HH:MM), answered_by (borrower|spouse|neighbour), borrower {name, voice: m1|m2|f}, third_party {voice: spouse_f|neighbour_m} (if any), facts {...}, hero, hard_negative, turns`. Voice codes (`borrower.voice`, `third_party.voice`) are legacy hints: the casting is one voice per role (voices.yaml), so every borrower is female and every agent and third party is male in the script.
Per turn: `s` = A (agent) | B (borrower) | T (third party); `t` = spoken text in Roman script (Hinglish; borrower/third party natural Mumbai-style Hinglish); optional `td` = the same line in Devanagari script, used for TTS when the text mode is Devanagari (`t` stays the Roman reference text and is what the labels `L` refer to); optional `tts_text` override; optional `L` = labels `[[RULE, "exact substring of t"], ...]`.
Label rules: `"*"` as the trigger means the whole turn / call-level. R1 label sits on the FIRST agent turn; R2 label sits on the SECOND agent turn; all other labels name the exact trigger phrase. Turn numbers = position in `turns` starting at 1.
Good-practice (G1) turns are not labelled; the evaluation does not score G1.

## Language rules (decided)
Borrower/third party = natural Mumbai-style Hinglish (Hindi grammar with English words used as people really say them). Agent = Hinglish. Coach = natural Hinglish, ≤ 14 words. All fictional names; lender is fictional ("Tarang Finserv", keep it in one constant). Amounts are written as words so TTS reads them right.

## Review by the user
The user may edit any `t:` line; then re-run only that scenario in notebook 02 (cache regenerates changed lines only).
