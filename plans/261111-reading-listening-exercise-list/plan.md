---
title: Reading and Listening exercise listing
status: completed
progress: 100%
priority: P1
effort: small
branch: feat/reading-listening-exercise-list
tags: [api, reading, listening]
created: 2026-11-11
---

# Reading and Listening exercise listing

## Context and scope

FastAPI already exposes generation and UUID-based detail routes. PostgreSQL
`Bank` verifies publication eligibility; the frontend proxy currently denies
collection GET requests and drops query strings. Add a summary list endpoint
and its proxy access. Replacing bank UI mocks and assembling full exams are
outside this change. Existing detail, generation, answers and trace contracts
must remain unchanged. No schema migration or new dependencies are needed.

## Contract and acceptance criteria

- `GET /api/exercises` returns `{items, total, limit, offset}`; empty lists and
  offsets beyond the last item still return the correct total.
- Optional `skill=reading|listening`, `target_band` (1–9, half-band steps), and
  `q` (literal case-insensitive title/topic substring, trimmed, at most 200
  characters, no NUL). Default `limit=20` (1–100), `offset=0` (0–2147483647).
- Sort newest first, breaking timestamp ties by item UUID descending.
- Summaries contain id, title, skill, topic, target_band, source, status,
  created_at, question_count and distinct sorted question_types. No passages,
  scripts, answers, evidence, explanations or model/trace metadata.
- Match existing publication gates: verified status, no excluded questions,
  all three recorded validator layers present and wholly passing.
- Apply existing bearer authentication and sanitized database error handling.
- Frontend `GET /api/backend/exercises` forwards list queries without changing
  forwarding behavior for other endpoints.

## Tasks

- [x] Review plan and publication/filter/pagination edge cases.
- [x] Add parameterized PostgreSQL listing and FastAPI route/query validation.
- [x] Open collection GET in frontend proxy and preserve list query strings.
- [x] Test API validation/auth/errors, PostgreSQL filters/publication/pagination,
  and proxy routing/query forwarding; check affected regressions.
- [x] Review changes, document API, write journal, and synchronize plan.

## Validation

- Backend non-Speaking suite: **733 passed**, no failures/skips/warnings;
  real PostgreSQL `ielts_test` with UUID-isolated schemas, including 44 API and
  34 bank cases. Windows connection/temp issues resolved using IPv4 and a
  dedicated temporary directory, without changing application code.
- Frontend: **138 passed** across 16 files; full ESLint and TypeScript checks
  passed. No new dependencies, migrations or UI changes.
- Independent plan and code reviews approved; `git diff --check` passed.
- All plan tasks reconciled; this plan has no separate phase files.
- User-authorized branch/commit workflow follows verification; no push requested.
