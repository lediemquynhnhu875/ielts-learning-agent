---
title: Reading and Listening practice attempts
status: completed
progress: 100%
priority: P1
effort: medium
tags: [backend, practice, grading]
created: 2026-11-03
---

# Reading and Listening practice attempts

## Scope and constraints

Add FastAPI endpoints for one verified content item's practice lifecycle: start,
resume, save partial answers, submit and read results. Use PostgreSQL, Pydantic,
existing bearer authentication and an attempt-specific capability token. Preserve
all generation/read APIs and Writing/Speaking behavior. Do not add UI, audio
generation, learner accounts, EXAM/EXAM_ITEM, answer sets or estimated IELTS bands.

## Plan

- [x] Add deterministic grading for the four existing question kinds: normalize
  Unicode/case/whitespace, require exact option labels, enforce completion word
  limits, count blanks wrong, report raw score/total/percentage and per-question
  correct answer, explanation, evidence and reason.
- [x] Add explicit development-schema extensions for practice attempts and answer
  rows. Snapshot the verified public content and private answer key at start;
  serialize mutations with row locks; persist submissions atomically.
- [x] Add create/read/save/submit routes and request/response schemas. Return no
  keys before submission. Validate all IDs before applying partial updates; reject
  edits after submission; duplicate submissions return the original result.
- [x] Verify normalization, blank/wrong/over-limit answers, invalid IDs, privacy,
  token isolation, persistence, retries and concurrent save/submit behavior, with
  regression coverage for existing backend contracts.
- [x] Review changes, document API examples and schema initialization, then sync
  plan and record decisions/limitations.

## Acceptance criteria

1. Start only verified Reading/Listening exercises; store one content item per attempt.
2. Resume persisted drafts without exposing key, trace or solver metadata.
3. PATCH merges supplied question responses; null/blank clears a response; foreign
   question IDs and malformed/oversized payloads fail without partially saving.
4. Submit merges final responses and grades all questions deterministically without
   an LLM; missing answers score zero and max score equals the question count.
5. Submission locks answers and result; retries are idempotent and races cannot
   overwrite a submitted attempt. Every result survives process restart.
6. Existing bearer requirement applies and each attempt requires its own secret
   token, returned only at creation; storage keeps only the token hash.
7. Partial practice reports no inferred IELTS band. Listening remains script-only.
8. Existing API response contracts remain unchanged. Tests use fake dependencies
   or isolated PostgreSQL schemas and never mutate the shared content database.

## Touchpoints and dependencies

New `backend/ielts_agent/practice/`, route and repository modules, additive SQL,
`api/main.py` wiring and `Bank.initialize()` SQL discovery. Existing public bank
projections remain compatible. No additional runtime dependencies.

## Completion evidence

All five checklist items are complete. No `phase-XX-*.md` files exist under this
plan, so there are no phase checkboxes left to reconcile. Full backend verification
with disposable PostgreSQL passed: 460 passed, 19 skipped, 15 subtests in 32.72s.
See [verification report](reports/verification.md) for scope and limitations.
