---
title: Automatic PostgreSQL migrations at startup
status: completed
progress: 100%
priority: P1
effort: small
tags: [backend, migrations]
created: 2026-11-03
---

# Automatic PostgreSQL migrations at startup

## Scope

Run pending numbered SQL migrations before the FastAPI app serves requests.
Default `DATABASE_AUTO_MIGRATE=true`; explicit false keeps manual CLI operation.
Retain existing content, attempts, endpoints and SQL files. No new dependencies,
frontend changes, shared database cleanup or changes to Writing/Speaking.

## Plan and acceptance

- [x] Add `uc04_schema_migration` ledger with filename, normalized-text SHA-256
  and timestamp. Apply pending scripts in order under the existing advisory lock
  in one transaction. Reject missing scripts, checksum drift and empty packages.
- [x] Call migrations from FastAPI lifespan in a worker thread before yielding;
  fail startup clearly without credentials on errors and always close agents.
- [x] Add strict boolean environment parsing and an explicit default-on setting.
  Keep the manual init command; injected test banks implement the initializer.
- [x] Verify default/disabled startup, startup failure/cleanup, one-time execution,
  legacy-schema adoption, CRLF normalization, rollback and concurrent migration
  runners with isolated PostgreSQL; run the full backend regression suite.
- [x] Review and update API/setup docs, environment example, journal and report.

## Review

Implementation plan reviewed and approved by the code-review agent. Use universal
newline SQL reads for cross-platform checksums and preserve the existing SQL
files. No user approval is needed for these authorized implementation changes.

## Completion evidence

All five checklist items complete; no phase files exist to reconcile. Full backend
verification with disposable PostgreSQL: 490 passed, 19 skipped, 15 subtests in
28.98s. Compile and diff checks passed; Docker Compose configuration validated.
Docker SQL entrypoint mount removed to avoid applying future migrations twice.
See [verification](reports/verification.md).
