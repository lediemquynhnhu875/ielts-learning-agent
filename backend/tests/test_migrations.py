"""Automatic startup and versioned SQL migration lifecycle checks."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import threading
import traceback

from fastapi.testclient import TestClient
import psycopg
import pytest

from ielts_agent.api.main import create_app
from ielts_agent.core.config import Settings
from ielts_agent.infrastructure.db.bank import Bank, BankNotInitializedError
from ielts_agent.infrastructure.db import migrations
from tests.test_api import ApiBank
from tests.test_bank import bank, _draft, _metadata, _request, _trace
from tests.test_pipeline import FakeAgents


class StartupBank(ApiBank):
    def __init__(self, error=None):
        super().__init__()
        self.error = error
        self.initialize_calls = 0
        self.worker_without_event_loop = False

    def initialize(self):
        self.initialize_calls += 1
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.worker_without_event_loop = True
        if self.error is not None:
            raise self.error


class ClosingAgents(FakeAgents):
    def __init__(self):
        super().__init__([])
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


def test_default_startup_migrates_before_health_and_closes_agents():
    repository, agents = StartupBank(), ClosingAgents()
    app = create_app(settings=Settings(), bank=repository, agents=agents)
    assert repository.initialize_calls == 0 and agents.close_calls == 0
    with TestClient(app) as client:
        assert repository.initialize_calls == 1
        assert repository.worker_without_event_loop
        assert client.get("/health").json() == {"status": "ok"}
        assert agents.close_calls == 0
    assert agents.close_calls == 1


def test_disabled_startup_skips_migrations_and_closes_agents():
    repository, agents = StartupBank(RuntimeError("Must not be called")), ClosingAgents()
    with TestClient(create_app(settings=Settings(database_auto_migrate=False), bank=repository, agents=agents)) as client:
        assert client.get("/health").status_code == 200
    assert repository.initialize_calls == 0 and agents.close_calls == 1


@pytest.mark.parametrize("error", [
    psycopg.OperationalError("RAW_STARTUP_SECRET database password"),
    BankNotInitializedError("RAW_STARTUP_SECRET missing table"),
    migrations.MigrationError("RAW_STARTUP_SECRET migration details"),
    OSError("RAW_STARTUP_SECRET unreadable migration"),
])
def test_startup_failure_is_sanitized_and_closes_agents(error):
    repository, agents = StartupBank(error), ClosingAgents()
    with pytest.raises(RuntimeError, match="Automatic PostgreSQL migration failed") as caught:
        with TestClient(create_app(settings=Settings(), bank=repository, agents=agents)):
            pytest.fail("An app with failed startup must not begin serving")
    assert repository.initialize_calls == agents.close_calls == 1
    assert "RAW_STARTUP_SECRET" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__suppress_context__


def test_agents_close_when_the_client_context_exits_with_an_error():
    agents = ClosingAgents()
    with pytest.raises(RuntimeError, match="caller stopped"):
        with TestClient(create_app(settings=Settings(), bank=StartupBank(), agents=agents)):
            raise RuntimeError("caller stopped")
    assert agents.close_calls == 1


def test_app_construction_and_module_import_do_not_open_database(monkeypatch):
    def no_connection(*args, **kwargs):
        pytest.fail("Import and construction must defer database connections to lifespan")

    monkeypatch.setattr(psycopg, "connect", no_connection)
    module = importlib.import_module("ielts_agent.api.main")
    reloaded = importlib.reload(module)
    assert reloaded.app is not None
    assert reloaded.create_app(settings=Settings(), agents=ClosingAgents()) is not None


@pytest.mark.parametrize("value,expected", [
    (None, True), ("", True), (" \t", True),
    ("true", True), ("1", True), ("YES", True), (" On ", True),
    ("false", False), ("0", False), ("NO", False), (" Off ", False),
])
def test_auto_migrate_environment_setting(value, expected, monkeypatch):
    # Isolate this setting from developer .env files and unrelated environment.
    config = importlib.import_module("ielts_agent.core.config")
    monkeypatch.setattr(config, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.delenv("GENERATOR_MAX_TOKENS", raising=False)
    monkeypatch.delenv("SOLVER_MAX_TOKENS", raising=False)
    if value is None:
        monkeypatch.delenv("DATABASE_AUTO_MIGRATE", raising=False)
    else:
        monkeypatch.setenv("DATABASE_AUTO_MIGRATE", value)
    assert Settings.from_env().database_auto_migrate is expected


def test_invalid_auto_migrate_environment_setting_fails_clearly(monkeypatch):
    config = importlib.import_module("ielts_agent.core.config")
    monkeypatch.setattr(config, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.setenv("DATABASE_AUTO_MIGRATE", "sometimes")
    with pytest.raises(ValueError, match="DATABASE_AUTO_MIGRATE must be a boolean"):
        Settings.from_env()


def _ledger(repository):
    with repository._connection() as connection:
        return {row["version"]: (row["checksum"], row["applied_at"])
                for row in connection.execute("SELECT version,checksum,applied_at FROM uc04_schema_migration")}


def _migration_directory(tmp_path, monkeypatch):
    for script in migrations.MIGRATIONS_DIRECTORY.glob("[0-9]*.sql"):
        (tmp_path / script.name).write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(migrations, "MIGRATIONS_DIRECTORY", tmp_path)
    return tmp_path


def test_migration_ledger_and_multiple_initializers_preserve_history(bank):
    original = _ledger(bank)
    expected = {script.name: hashlib.sha256(script.read_text(encoding="utf-8").encode()).hexdigest()
                for script in migrations.MIGRATIONS_DIRECTORY.glob("[0-9]*.sql")}
    assert original.keys() == expected.keys()
    assert {version: checksum for version, (checksum, _at) in original.items()} == expected
    assert all(applied_at.tzinfo is not None for _checksum, applied_at in original.values())
    bank.initialize()
    Bank(bank.database_url).initialize()
    assert _ledger(bank) == original


def test_pending_non_idempotent_migration_executes_once(bank, tmp_path, monkeypatch):
    directory = _migration_directory(tmp_path, monkeypatch)
    (directory / "003_once.sql").write_text(
        "CREATE TABLE migration_once (id integer PRIMARY KEY); INSERT INTO migration_once VALUES (1);", encoding="utf-8"
    )
    bank.initialize()
    applied = _ledger(bank)
    assert "003_once.sql" in applied
    Bank(bank.database_url).initialize()
    bank.initialize()
    assert _ledger(bank) == applied
    with bank._connection() as connection:
        assert connection.execute("SELECT id FROM migration_once").fetchall() == [{"id": 1}]


def test_legacy_001_schema_upgrades_on_startup_without_content_loss(bank):
    draft = _draft()
    exercise = bank.save_verified(_request(), draft, _metadata(), _trace(draft))
    answers = bank.get_answers(exercise["id"])
    # Only this fixture's UUID schema is affected. It now represents a legacy
    # install with 001's tables/data but no practice tables or migration ledger.
    with bank._connection() as connection:
        connection.execute("DROP TABLE listening_audio")
        connection.execute("DROP TABLE practice_answer")
        connection.execute("DROP TABLE practice_attempt")
        connection.execute("DROP TABLE uc04_schema_migration")
    with TestClient(create_app(settings=Settings(), bank=bank, agents=ClosingAgents())) as client:
        assert client.get("/health").status_code == 200
    assert bank.get_item(exercise["id"]) == exercise
    assert bank.get_answers(exercise["id"]) == answers
    assert set(_ledger(bank)) == {"001_uc04.sql", "002_practice.sql", "003_listening_audio.sql"}
    with bank._connection() as connection:
        assert connection.execute("SELECT count(*) AS count FROM practice_attempt").fetchone()["count"] == 0


def test_first_startup_creates_tables_in_an_empty_isolated_schema(bank):
    # This bank fixture owns a separate UUID-named schema, never the shared one.
    with bank._connection() as connection:
        connection.execute(
            """DROP TABLE listening_audio, practice_answer, practice_attempt, validation_result,
               question, question_group, content_item, uc04_trace, uc04_schema_migration"""
        )
    with TestClient(create_app(settings=Settings(), bank=bank, agents=ClosingAgents())) as client:
        assert client.get("/health").status_code == 200
        draft = _draft()
        exercise = bank.save_verified(_request(), draft, _metadata(), _trace(draft))
        response = client.post(f"/api/exercises/{exercise['id']}/attempts")
        assert response.status_code == 201
        assert response.json()["status"] == "in_progress"
    assert set(_ledger(bank)) == {"001_uc04.sql", "002_practice.sql", "003_listening_audio.sql"}


def test_failed_pending_batch_rolls_back_schema_and_ledger_then_can_retry(bank, tmp_path, monkeypatch):
    directory = _migration_directory(tmp_path, monkeypatch)
    original = _ledger(bank)
    (directory / "003_pending.sql").write_text("CREATE TABLE migration_pending (id integer);", encoding="utf-8")
    bad_script = directory / "004_failure.sql"
    bad_script.write_text("SELEC this_is_invalid_sql;", encoding="utf-8")
    with pytest.raises(psycopg.Error):
        bank.initialize()
    assert _ledger(bank) == original
    with bank._connection() as connection:
        assert connection.execute("SELECT to_regclass('migration_pending') AS table_name").fetchone()["table_name"] is None
    bad_script.write_text("INSERT INTO migration_pending VALUES (1);", encoding="utf-8")
    bank.initialize()
    assert set(_ledger(bank)) == {*original, "003_pending.sql", "004_failure.sql"}
    with bank._connection() as connection:
        assert connection.execute("SELECT id FROM migration_pending").fetchall() == [{"id": 1}]


@pytest.mark.parametrize("defect", ["modified", "missing"])
def test_applied_migration_changes_fail_before_new_sql(bank, tmp_path, monkeypatch, defect):
    directory = _migration_directory(tmp_path, monkeypatch)
    original = _ledger(bank)
    first_script = directory / "001_uc04.sql"
    if defect == "modified":
        first_script.write_text(first_script.read_text(encoding="utf-8") + "\n-- changed\n", encoding="utf-8")
    else:
        first_script.unlink()
    (directory / "003_never.sql").write_text("CREATE TABLE migration_never (id integer);", encoding="utf-8")
    with pytest.raises(migrations.MigrationError):
        bank.initialize()
    assert _ledger(bank) == original
    with bank._connection() as connection:
        assert connection.execute("SELECT to_regclass('migration_never') AS table_name").fetchone()["table_name"] is None


def test_migration_checksum_ignores_windows_line_endings(bank, tmp_path, monkeypatch):
    directory = _migration_directory(tmp_path, monkeypatch)
    original = _ledger(bank)
    for script in directory.glob("[0-9]*.sql"):
        script.write_bytes(script.read_text(encoding="utf-8").replace("\n", "\r\n").encode())
    bank.initialize()
    assert _ledger(bank) == original


def test_empty_migration_package_is_rejected_without_changing_ledger(bank, tmp_path, monkeypatch):
    original = _ledger(bank)
    monkeypatch.setattr(migrations, "MIGRATIONS_DIRECTORY", tmp_path)
    with pytest.raises(migrations.MigrationError, match="No numbered SQL migration files"):
        bank.initialize()
    assert _ledger(bank) == original


def test_concurrent_initializers_apply_new_sql_once(bank, tmp_path, monkeypatch):
    directory = _migration_directory(tmp_path, monkeypatch)
    (directory / "003_concurrent.sql").write_text(
        "CREATE TABLE migration_concurrent (id integer PRIMARY KEY); INSERT INTO migration_concurrent VALUES (1);",
        encoding="utf-8",
    )
    barrier = threading.Barrier(2)

    def initialize():
        barrier.wait(timeout=10)
        Bank(bank.database_url).initialize()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.submit(initialize), executor.submit(initialize)
        first.result(timeout=15)
        second.result(timeout=15)
    assert "003_concurrent.sql" in _ledger(bank)
    with bank._connection() as connection:
        assert connection.execute("SELECT id FROM migration_concurrent").fetchall() == [{"id": 1}]
