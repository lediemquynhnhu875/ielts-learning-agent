---
title: Azure Speech Listening synthesis
status: completed
progress: 100%
---

Use Azure Speech REST synthesis with escaped SSML voice elements in turn order,
return one WAV file, and reuse existing AZURE_SPEECH_KEY/REGION configuration.

- [x] Add configured British voice defaults and explicit speaker-ID overrides.
- [x] Bound script/SSML/voice-tag size, HTTP timeout and audio output; validate WAV.
- [x] Add authenticated POST /api/listening/audio and POST /api/exercises/{item_id}/audio without changing existing responses.
- [x] Test via injected HTTP transport, including XML injection, provider errors, configuration, authentication and unchanged original APIs.
- [x] Review and document configuration, examples and verification.

No frontend, database migration, audio persistence/cache or automatic commit/push in this slice. Never expose credentials/provider error bodies. No retries that could repeat billable synthesis. Live synthesis was performed separately at the user's explicit request after configuration.

## Verification

Plan and production code reviewed independently. Fixed malformed RIFF chunk
traversal raising RuntimeError so invalid audio returns 502 rather than 500.
Review approved after fix. HTTP timeout is 120-second I/O inactivity plus elapsed
checks between chunks, not a hard total deadline. WAV bounds reject >=599 seconds.

`.venv/Scripts/python.exe -m pytest backend/tests --ignore=backend/tests/speaking -q -rs`:
**482 passed, 29 skipped** in 11.09s, including 43 new offline Azure tests.
All skips require TEST_DATABASE_URL. Speaking excluded. Compile and diff checks
passed.

Live smoke test on 2026-11-10, after the user configured credentials and network
sandbox approval: one actual Azure POST via TestClient /api/listening/audio
returned Azure/API 200. Three turns/two speakers with Ryan/Sonia completed in
3.69s; WAV is 12.55s, 602444 bytes, PCM mono 24000Hz/16bit, with no-store.
Storage/agents were fake to avoid PostgreSQL; Azure was real. Local WAV and JSON
metadata are under ignored data/listening/. No credentials were recorded.
This verifies authentication, selected voices, API response and audio format.

A subsequent real PostgreSQL smoke run selected `Welcome to Lotus Residence,
Can Tho`, item `0452ee07-8baf-4430-a63f-521b64e22b28` (band 6.0, 592 words,
10 questions). Actual Bank GET item/turns and POST `/api/exercises/{id}/audio`
returned Azure/API 200: 15 turns, Warden/Student; WAV 208.137s, 9990644 bytes,
mono 24000Hz/16bit, nonzero PCM, no-store. Elapsed 118.48s includes read API
calls. Item equality before/after proves no content mutation. The stopped local
Compose DB was started with its existing persisted volume; auto-migrate stayed
disabled. Ignored artifacts are `data/listening/azure-db-0452ee07-8baf-4430-a63f-521b64e22b28.wav`
and matching JSON. Stored-exercise integration is verified; subjective listening
quality has not been assessed.

All five checklist items reconciled; no phase files to synchronize. Existing
completed plans unchanged. API examples and provider references are in
[Azure Speech Listening docs](../../docs/listening-azure-speech.md).
