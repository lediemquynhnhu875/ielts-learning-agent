---
date: 2026-11-03
status: passed
---

# Reading/Listening practice verification

## Evidence

Final full-backend run used a disposable PostgreSQL instance and isolated test
schemas: **460 passed, 19 skipped, 15 subtests in 32.72s**. No failing tests.
Command shape, with the temporary database URL deliberately omitted:

```powershell
$env:TEST_DATABASE_URL = '<temporary PostgreSQL test database URL>'
.\.venv\Scripts\python.exe -m pytest -q backend/tests
```

| Check | Result |
|---|---|
| Practice HTTP contracts | 45 cases passed |
| Deterministic grader | 38 cases passed |
| PostgreSQL repository | Persistence, rollback, frozen snapshots and concurrent save/submit verified |
| Real HTTP with PostgreSQL | Start → save → recreate app → submit → recreate app → read persisted result verified |
| Existing backend behavior | Full suite passed, including generation/read contracts and available Speaking coverage |
| Code review | Approved after Unicode/NUL payload hardening |
| Compile and whitespace checks | `compileall` and `git diff --check` passed |

The 19 skips concern optional test prerequisites; existing Speaking tests skip
when external audio fixtures or `database-design.docx` are absent. No per-reason
counts were recorded. The PostgreSQL practice integration checks did execute.

## Scope and completion

All five plan checklist items are complete; no phase files exist to sync. API
documentation, README/architecture links and the technical journal are updated.
No stage or commit was performed. Concurrent `frontend/package-lock.json` changes
were preserved and are outside this backend task.

The disposable PostgreSQL container was stopped and removed after verification;
tests did not mutate the shared content database. Remaining product boundaries:
script-only Listening, single-content-item practice, no inferred IELTS band,
no learner account integration, and no UI changes.
