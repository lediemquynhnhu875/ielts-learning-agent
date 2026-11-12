# Startup migration verification

## Result

Full backend suite against disposable PostgreSQL: **490 passed, 19 skipped,
15 subtests passed in 28.98s**. Optional Speaking fixture/design-document tests
remain skipped. All migration and existing bank/practice integration tests ran.

```powershell
$env:TEST_DATABASE_URL = '<disposable PostgreSQL test database URL>'
python -m pytest -q backend/tests
```

## Evidence

- Default startup migrates before serving, on a worker thread; opt-out skips it.
- Import/construction does not connect to the database. Failure stops startup,
  sanitizes details and closes agents; successful shutdown also closes agents.
- Empty isolated schema creates all content/practice tables and accepts a new
  attempt. Legacy 001 tables gain 002 and ledger without losing content or keys.
- Applied scripts run once across app restarts and concurrent initializers.
- Failed SQL rolls back the entire pending batch, including DDL and ledger.
- Modified/missing files and empty packages fail; CRLF/LF checksums match.
- Previous generation, practice lifecycle and Speaking tests remain passing.

Compileall, `git diff --check` and `docker compose config --quiet` passed. Removed
the Compose SQL entrypoint mount so the API owns migration execution. Disposable
test container had no data volume and was stopped/removed after validation.

## Scope

No new dependency or shared-database modification. Existing uncommitted changes
from the preceding practice feature and the concurrent frontend lockfile change
were preserved. No staging or commit was performed. Plan/checklists synchronized;
no phase files exist. Database must already exist and be reachable at startup.
