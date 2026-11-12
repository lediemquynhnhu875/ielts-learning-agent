"""Versioned SQL migrations, serialized and committed with their caller's transaction."""

import hashlib
from pathlib import Path

import psycopg


MIGRATIONS_DIRECTORY = Path(__file__).with_name("sql")
MIGRATION_LOCK_KEY = 0x55433034


class MigrationError(RuntimeError):
    pass


def apply_migrations(connection: psycopg.Connection) -> None:
    scripts = sorted(MIGRATIONS_DIRECTORY.glob("[0-9]*.sql"))
    if not scripts:
        raise MigrationError("No numbered SQL migration files were found")
    # read_text normalizes CRLF/LF, so the same checkout has one checksum on
    # Windows and inside the Linux container.
    pending = {script.name: script.read_text(encoding="utf-8") for script in scripts}
    checksums = {version: hashlib.sha256(text.encode("utf-8")).hexdigest()
                 for version, text in pending.items()}
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_KEY,))
    connection.execute(
        """CREATE TABLE IF NOT EXISTS uc04_schema_migration (
            version text PRIMARY KEY,
            checksum text NOT NULL CHECK (length(checksum) = 64),
            applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    applied = {row["version"]: row["checksum"] for row in connection.execute(
        "SELECT version,checksum FROM uc04_schema_migration"
    )}
    if applied.keys() - pending.keys():
        raise MigrationError("A previously applied SQL migration file is missing")
    for version, checksum in applied.items():
        if checksums[version] != checksum:
            raise MigrationError(f"Applied SQL migration {version} was modified; add a new migration instead")
    for version, text in pending.items():
        if version not in applied:
            connection.execute(text)
            connection.execute(
                "INSERT INTO uc04_schema_migration(version,checksum) VALUES (%s,%s)",
                (version, checksums[version]),
            )
