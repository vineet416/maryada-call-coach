# Spike results

Date: 2026-10-30. Script: `tools/spike.py`. All lines are synthetic turns taken from `content/scenarios` (10 agent, 10 borrower), spoken with Gnani Timbre V3.0 at 8 kHz and sent back through Gnani Prisma V3.0.

## Decision

**GO.** Agent-turn keyword recovery is 96-98% (threshold 80%) and borrower-turn recovery is 74-82% (threshold 60%). No change to the architecture.

## Chosen STT profile

| Role | Language setting | Adapter |
|---|---|---|
| agent | `hi-IN` | realtime (default), REST as per-turn fallback |
| borrower | `hi-IN` | realtime, REST fallback |
| third party | `hi-IN` | realtime, REST fallback |

Model id: `prisma-v3.0`. `hi-IN` was equal or better than auto-detection for every role in this run, and `mr-IN` was not better for the Marathi-flavoured borrower lines (75.5% vs 79.5%). The audition in the audio step re-checks this on the final voices before the profile file is written.

## Keyword recovery

Key terms per line: up to 5 content words. Matching compares consonant skeletons, so a Roman term and its Devanagari spelling count as the same word (edit distance of at most 1). This is an approximate score on 10 lines per role from a single run; treat differences of a few points as noise.

| Mode | Setting | Agent | Borrower | Latency |
|---|---|---|---|---|
| REST | `indic-auto` + `multi_lang_codes=hi-IN,mr-IN,en-IN` | 0.96 | 0.755 | 0.41 s median |
| REST | `indic-auto` + `multi_lang_codes=hi-IN,en-IN` | 0.96 | 0.795 | 0.40 s |
| REST | `hi-IN` | 0.96 | 0.795 | 0.40 s |
| REST | `mr-IN` | n/a | 0.755 | 0.39 s |
| Realtime | `indic-auto` | 0.96 | 0.735 | 0.26 s per segment (p95 0.41 s) |
| Realtime | `indic-auto` + `x-language-candidates` | 0.96 | 0.735 | 0.27 s (p95 0.45 s) |
| Realtime | `hi-IN` | 0.96-0.98 | 0.795-0.82 | 0.25 s (p95 0.37 s) |

Euri `gpt-5.4-mini` chat completions with `response_format: json_object`: 20 of 20 replies were valid JSON. Round trip median 1.2-1.4 s over two runs; p95 3.1 s in one run and 9.0 s in the other (a single slow call), so the engine needs its timeout and prefilter-only fallback.

## API facts that differ from the documentation assumptions

**Timbre TTS** (`POST /api/v1/tts/inference`, header `x-api-key-id`)
- Body: `text, voice, model, language, speed, audio_config`. `audio_config` that works: `{"encoding": "linear_pcm", "sample_rate": 8000, "container": "wav"}`. The response is a mono 16-bit WAV at 8 kHz, so no resampling is needed for phone-style audio.
- An unsupported model returns 400 and lists the supported ones (`timbre-v2.5`, `timbre-v3.0`).
- Only **one active request per key at a time**; a second concurrent request returns 429 `RATE_LIMITED`. Generation must be sequential.
- A request of 1000 characters was accepted, so the 600-character split stays a conservative choice rather than a hard limit.
- A line starting with an `<angry>` tag returned 200. Whether it changes the voice is decided by listening in the audition.

**Prisma STT, REST** (`POST /stt/v3`, header `X-API-Key-ID`, multipart)
- The file field is `audio_file`. Form fields: `model=prisma-v3.0`, `language_code`, and `multi_lang_codes` (comma-separated). `language_code=indic-auto` without `multi_lang_codes` returns 400 `INVALID_LANGUAGE_CODE`.
- Response JSON: `transcript`, `detected_language_code`, `processing_time`, `end_to_end_latency`.
- Only one active request at a time (429 otherwise).
- An `output_mode` field (`codemix`, `transcribe`, `verbatim`) was accepted without error but made no measurable difference; it is not used.

**Prisma STT, realtime** (`wss://api.vachana.ai/stt/v3/stream`)
- Headers that work: `x-api-key-id`, `model`, `language_code`, `x-sample-rate`, optional `x-language-candidates` (both `hi-IN,mr-IN,en-IN` and `hi,mr,en` are accepted; no measurable effect).
- Messages: `connected`, `speech_start`, then `transcript` with `is_final`, `latency` (ms), `segment_index`, `audio_duration_ms`, `detected_language_code`. The server splits one turn into several final segments, and no end marker follows `commit`, so the client collects segments until about 2 s of silence.
- 20 parallel connections ran without errors. One of roughly 60 connections closed with code 1011; the REST adapter covers such a failure.
- Hindi and English words are returned mostly in Devanagari with `indic-auto`, and in a Roman/Devanagari mix with `hi-IN` ("EMI pending"). Matching must handle both scripts.

**Euri** (`POST /chat/completions`, bearer token): JSON mode works with `gpt-5.4-mini`; the fallback model was not exercised in this spike.

## Limits of this spike
Single run, 20 lines, one voice per role, approximate scoring. It decides go/no-go and the starting profile, not final accuracy; the evaluation step measures that on the full call set.
