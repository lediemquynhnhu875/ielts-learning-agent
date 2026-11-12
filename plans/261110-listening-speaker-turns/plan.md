---
title: Listening speaker turns
status: completed
progress: 100%
---

Implement deterministic script segmentation for downstream Azure voice assignment.

- [x] Parse explicit line-start speaker labels and common inline role labels, preserving speech order and source offsets.
- [x] Return stable speaker IDs, labels, and ordered turns; unlabelled speech uses Narrator. Reject blank scripts and empty labelled turns.
- [x] Expose authenticated POST /api/listening/turns and GET /api/exercises/{item_id}/listening-turns; GET rejects non-Listening items.
- [x] Test parser boundaries, punctuation, multiline and inline dialogue, API validation/authentication and existing API compatibility.
- [x] Review and document the contract and limits.

Keep source text, database schemas, generation, grading, and existing responses unchanged. No LLM calls, Azure calls, voice selection, audio, or frontend changes in this slice.

## Review and verification

Plan and implementation reviewed by the code-review agent. Compound labels now
suppress nested role matches so turns never contain overlapping/negative spans.
Titlecase colon prefixes use a documented label grammar; ambiguous headings are
not inferred automatically.

Second review fixes normalize spaces/tabs when matching known multiword names,
recognize apostrophe names such as `O'Connor:` and bare CR line endings, and
sanitize route-local validation errors so malformed Unicode JSON returns 422
instead of a response-encoding failure. Source offsets remain unchanged.

Latest second-review verification:
`.venv/Scripts/python.exe -m pytest backend/tests --ignore=backend/tests/speaking -q -rs`
completed with **439 passed, 29 skipped** in 9.64s, including 37 Listening
parser/API tests (9 added regression cases). Adversarial review found no
additional issues; 100,000-character probes showed no catastrophic regex behavior.
PostgreSQL integration tests need `TEST_DATABASE_URL`; Speaking was outside this
change's touchpoints. Compilation and `git diff --check` passed.

All checklist items reconciled; this plan and the existing completed plans have
no phase files requiring synchronization. See
[API contract](../../docs/listening-speaker-turns.md).
