---
title: Listening audio STT verification
status: completed
progress: 100%
---

Recognize synthesized audio once with Azure Speech continuous recognition and
compare the transcript against spoken turns only (no labels, no reference prompt).
Reuse Azure key/region. Preserve successful WAV format and source exercise/key
content. The screenshot intentionally changes stored-audio delivery to require
verification and adds audio artifact persistence.

- [x] Add Azure STT adapter using optional Speech SDK, complete-file recognition, safe errors and time/resource bounds.
- [x] Add deterministic word alignment with exact Levenshtein WER, counts and grouped differences; normalize case/Unicode/punctuation, retain lexical number/name differences.
- [x] Add POST /api/listening/audio/verify and POST /api/exercises/{item_id}/audio/verify returning WAV base64 plus transcript/comparison; preflight STT before paid TTS.
- [x] Add CLI for comparing an existing WAV with a reference text file, avoiding repeat synthesis.
- [x] Test alignment, full-file STT/events/errors, injected pipeline, auth and existing API contracts; review and document limits.
- [x] Run one live STT on the already generated DB WAV when configured, preserving its reference text and exporting local report.
- [x] Extended screenshot requirement: anchor each private answer/evidence to independently measured TTS timing, validate number/spelling correctness, and fail closed on missing or ambiguous evidence.
- [x] Extended screenshot requirement: persist audio/timing/verification with the exercise and block learner delivery of failed or unverified audio.

No frontend, automatic retries, correction of source/audio or automatic
regeneration. No automatic commit/push. STT mismatch requires review and does
not establish whether synthesis or recognition is at fault. The later screenshot
authorizes additive audio/timing persistence and a delivery gate.

## Original diagnostic phase evidence

Code review approved. SDK cancellation handling was corrected after the live run
exposed that real EOF details are in `event.cancellation_details`, not top-level
`event.reason`; realistic regression fixtures now exercise this shape.

Full non-Speaking backend suite: **552 passed, 29 skipped** (TEST_DATABASE_URL),
including 28 adapter and 42 comparison/pipeline/API/CLI tests. Compile and diff
checks pass. Actual Azure STT completed on the existing 208.137-second DB WAV;
586 reference tokens, 588 transcript tokens, S=18, D=1, I=3, WER=0.037543.
Many differences are display forms such as nine/9, fourth/4th and Can Tho/Cantho.
Report: ignored `data/listening/azure-db-0452ee07-8baf-4430-a63f-521b64e22b28-verification.json`.

## Scope clarification after screenshot

The screenshot adds timed per-answer verification and a delivery gate beyond
whole-transcript diagnostics, plus audio/timing persistence. Treat the screenshot
as acceptance criteria and add the prerequisite independent TTS timings. The
user explicitly selected the complete pipeline including persistence and gates. Existing
whole-transcript reports alone do NOT establish these criteria and must not be
treated as an audio publication decision.
No timestamps may be guessed from text proportions or STT answer search itself;
no global WER threshold can replace checking every required answer.

## Extended implementation

1. TTS each parsed turn to fixed PCM WAV, concatenate PCM and measure turn windows
   directly from frame counts. Store script/turn offsets with those windows.
2. STT detailed lexical words with SDK audio offsets; preserve the text-only API.
3. For each private answer, anchor its unique source evidence and check aligned
   lexical words inside independently measured turn windows. Treat numeric values
   canonically, check spelling sequences, and fail closed on ambiguity/missing data.
4. Persist immutable bindings (source/key hash, audio hash, voice config), WAV,
   timing manifest and verification in an additive PostgreSQL audio table.
5. Stored-exercise audio endpoints return bytes only for matching, verified
   artifacts. Failed/unverifiable results return diagnostics without audio bytes.
   Raw-script generation remains an authoring preview, not learner delivery.

## Final verification

All eight checklist items reconciled; no phase files need synchronization.
Extended code review approved after closing number/negation/spelling false passes,
per-word own-turn checks, active configuration binding, manifest integrity and
public timing-field filtering. Existing source text and private answer keys stay
unchanged. Authoring routes require a configured server-side API_TOKEN.

Full backend suite excluding Speaking, with isolated PostgreSQL schemas:
**698 passed, 0 skipped** in 29.62s. Compilation and diff checks passed.
The initial Windows temporary-directory permission errors were resolved using a
unique workspace-local pytest temporary directory; no application fix was needed.

Actual stored-exercise publishing was exercised with item
`0452ee07-8baf-4430-a63f-521b64e22b28`: 15 Azure TTS calls returned 200; detailed
STT completed; 9,990,644 WAV bytes and 15 measured turn windows were persisted.
Three answer checks passed, six failed, one was unverifiable, so status is
blocked. Actual audio/timing GETs both returned 409 and the authoring response
contained no audio base64. Source/key hash before and after matched. Elapsed:
266.04 seconds. These are recognition-check outcomes, not proof of six TTS faults.

See [verification guide](../../docs/listening-audio-verification.md) and the
ignored local authoring report
`data/listening/azure-publication-0452ee07-8baf-4430-a63f-521b64e22b28.json`.
