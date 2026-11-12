"""Practice storage checks use only the isolated TEST_DATABASE_URL schema."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import threading
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
import pytest
from fastapi.testclient import TestClient

from ielts_agent.api.main import create_app
from ielts_agent.core.config import Settings
from ielts_agent.infrastructure.db.bank import Bank
from ielts_agent.infrastructure.db.practice import PostgresAttemptStore
from tests.test_api import AUTH, TOKEN
from tests.test_bank import bank, _draft, _metadata, _request, _trace
from tests.test_pipeline import FakeAgents


def _record(bank):
    draft = _draft()
    exercise = bank.save_verified(_request(), draft, _metadata(), _trace(draft))
    key = bank.get_answers(exercise["id"])
    return {
        "attempt_id": str(uuid4()), "item_id": exercise["id"], "skill": "reading",
        "status": "in_progress", "token_hash": hashlib.sha256(b"test-secret").hexdigest(),
        "exercise_snapshot": exercise, "answer_key_snapshot": key, "answers": {},
        "started_at": datetime.now(timezone.utc), "submitted_at": None,
        "result": None, "raw_score": None,
    }


def _finish(record):
    questions = [
        question for group in record["exercise_snapshot"]["question_groups"]
        for question in group["questions"]
    ]
    record["status"] = "submitted"
    record["submitted_at"] = record["started_at"] + timedelta(seconds=20)
    record["raw_score"] = 0
    record["result"] = {
        "grading_version": "fixed-key-v1", "raw_score": 0,
        "questions": [{"question_id": question["id"], "is_correct": False}
                      for question in questions],
    }
    for question in questions:
        record["answers"].setdefault(question["id"], "")


def test_source_content_and_key_are_read_from_one_snapshot(bank, monkeypatch):
    record = _record(bank)
    original = Bank._get_item
    question_id = record["answer_key_snapshot"]["answers"][0]["question_id"]

    def get_item_then_change_key(connection, item_id):
        exercise = original(connection, item_id)
        with psycopg.connect(bank.database_url) as writer:
            writer.execute(
                "UPDATE question SET answer_key=%s WHERE id=%s",
                (Jsonb({"answer": "FALSE", "explanation": "Changed later."}), question_id),
            )
        return exercise

    monkeypatch.setattr(Bank, "_get_item", staticmethod(get_item_then_change_key))
    exercise, key = PostgresAttemptStore(bank).load_source(record["item_id"])
    assert exercise == record["exercise_snapshot"]
    assert key == record["answer_key_snapshot"]
    assert bank.get_answers(record["item_id"])["answers"][0]["answer_key"] == "FALSE"


def test_drafts_and_results_survive_store_recreation_and_schema_rerun(bank):
    record = _record(bank)
    store = PostgresAttemptStore(bank)
    store.create(record)
    assert PostgresAttemptStore(bank).get(record["attempt_id"]) == record
    question_id = record["answer_key_snapshot"]["answers"][0]["question_id"]
    with store.edit(record["attempt_id"]) as draft:
        draft["answers"][question_id] = "TRUE"
    bank.initialize()
    with PostgresAttemptStore(bank).edit(record["attempt_id"]) as draft:
        assert draft["answers"] == {question_id: "TRUE"}
        _finish(draft)
        submitted = deepcopy(draft)
    assert PostgresAttemptStore(bank).get(record["attempt_id"]) == submitted
    with psycopg.connect(bank.database_url) as connection:
        rows = connection.execute(
            "SELECT is_correct FROM practice_answer WHERE attempt_id=%s",
            (record["attempt_id"],),
        ).fetchall()
    assert len(rows) == 10 and all(row == (False,) for row in rows)


def test_invalidated_content_cannot_start_new_attempt_but_snapshot_remains(bank):
    record = _record(bank)
    store = PostgresAttemptStore(bank)
    store.create(record)
    with psycopg.connect(bank.database_url) as connection:
        connection.execute("UPDATE content_item SET status='rejected' WHERE item_id=%s", (record["item_id"],))
    assert store.load_source(record["item_id"]) is None
    assert store.load_source(str(uuid4())) is None
    assert store.get(record["attempt_id"]) == record
    assert store.get(str(uuid4())) is None


def test_failed_edit_rolls_back_answers_and_submission(bank):
    record = _record(bank)
    store = PostgresAttemptStore(bank)
    store.create(record)
    question_id = record["answer_key_snapshot"]["answers"][0]["question_id"]
    with pytest.raises(RuntimeError, match="abort edit"):
        with store.edit(record["attempt_id"]) as draft:
            draft["answers"][question_id] = "FALSE"
            _finish(draft)
            raise RuntimeError("abort edit")
    assert store.get(record["attempt_id"]) == record


def test_late_edits_cannot_change_a_persisted_submission(bank):
    record = _record(bank)
    store = PostgresAttemptStore(bank)
    store.create(record)
    with store.edit(record["attempt_id"]) as draft:
        _finish(draft)
    original = store.get(record["attempt_id"])
    with store.edit(record["attempt_id"]) as draft:
        draft["raw_score"] = 10
        draft["result"]["raw_score"] = 10
        draft["answers"] = {}
    assert store.get(record["attempt_id"]) == original


def test_source_content_deletion_cannot_cascade_practice_history(bank):
    record = _record(bank)
    store = PostgresAttemptStore(bank)
    store.create(record)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with psycopg.connect(bank.database_url) as connection:
            connection.execute("DELETE FROM content_item WHERE item_id=%s", (record["item_id"],))
    assert store.get(record["attempt_id"]) == record


def test_snapshot_question_response_remains_writable_after_source_question_deletion(bank):
    record = _record(bank)
    store = PostgresAttemptStore(bank)
    store.create(record)
    question_id = record["answer_key_snapshot"]["answers"][0]["question_id"]
    with psycopg.connect(bank.database_url) as connection:
        connection.execute("DELETE FROM question WHERE id=%s", (question_id,))
    with store.edit(record["attempt_id"]) as draft:
        draft["answers"][question_id] = "TRUE"
        _finish(draft)
    assert store.get(record["attempt_id"])["answers"][question_id] == "TRUE"


def test_concurrent_mutations_see_the_committed_submission_after_row_lock(bank):
    record = _record(bank)
    store = PostgresAttemptStore(bank)
    store.create(record)
    first_locked, second_started, release_first = (threading.Event() for _ in range(3))

    def submit():
        with store.edit(record["attempt_id"]) as draft:
            first_locked.set()
            assert release_first.wait(timeout=10)
            _finish(draft)

    def late_save():
        assert first_locked.wait(timeout=10)
        second_started.set()
        with PostgresAttemptStore(bank).edit(record["attempt_id"]) as draft:
            return draft["status"], deepcopy(draft["result"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        submitting = executor.submit(submit)
        saving = executor.submit(late_save)
        try:
            assert second_started.wait(timeout=10)
        finally:
            release_first.set()
        submitting.result(timeout=10)
        status, result = saving.result(timeout=10)
    assert status == "submitted"
    assert result == store.get(record["attempt_id"])["result"]


def test_answer_item_must_match_attempt_item(bank):
    record = _record(bank)
    store = PostgresAttemptStore(bank)
    store.create(record)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with psycopg.connect(bank.database_url) as connection:
            connection.execute(
                """INSERT INTO practice_answer(attempt_id,item_id,question_id,response)
                   VALUES (%s,%s,%s,'TRUE')""",
                (record["attempt_id"], str(uuid4()), str(uuid4())),
            )


def test_http_attempt_draft_and_result_survive_app_recreation(bank):
    """Exercise real routes, service and PostgreSQL together in an isolated schema."""
    draft = _draft()
    exercise = bank.save_verified(_request(), draft, _metadata(), _trace(draft))
    answer_key = bank.get_answers(exercise["id"])["answers"]
    expected_answers = {answer["question_id"]: answer["answer_key"] for answer in answer_key}
    first_half = {answer["question_id"]: answer["answer_key"] for answer in answer_key[:5]}
    last_half = {answer["question_id"]: answer["answer_key"] for answer in answer_key[5:]}

    def app():
        # Default repository wiring must use the injected PostgreSQL bank.
        return create_app(settings=Settings(api_token=TOKEN), bank=bank, agents=FakeAgents([]))

    with TestClient(app()) as client:
        created = client.post(f"/api/exercises/{exercise['id']}/attempts", headers=AUTH)
        assert created.status_code == 201, created.text
        attempt = created.json()
        attempt_id = attempt["attempt_id"]
        path = f"/api/attempts/{attempt_id}"
        headers = {**AUTH, "X-Attempt-Token": attempt["attempt_token"]}
        assert attempt["result"] is None and attempt["answers"] == {}
        assert "trace_id" not in attempt["exercise"] and "model" not in attempt["exercise"]
        saved = client.patch(path + "/answers", headers=headers, json={"answers": first_half})
        assert saved.status_code == 200 and saved.json()["answers"] == first_half

    with TestClient(app()) as restarted:
        resumed = restarted.get(path, headers=headers)
        assert resumed.status_code == 200 and resumed.json()["answers"] == first_half
        assert resumed.json()["status"] == "in_progress" and resumed.json()["result"] is None
        submitted = restarted.post(path + "/submit", headers=headers, json={"answers": last_half})
        assert submitted.status_code == 200, submitted.text
        result = submitted.json()
        assert result["status"] == "submitted" and result["answers"] == expected_answers
        assert result["result"]["raw_score"] == result["result"]["total_questions"] == 10
        assert result["result"]["percentage"] == 100 and result["result"]["band"] is None
        assert "attempt_token" not in result
        retry = restarted.post(path + "/submit", headers=headers,
                               json={"answers": {next(iter(expected_answers)): "wrong"}})
        assert retry.status_code == 200 and retry.json() == result
        assert restarted.patch(path + "/answers", headers=headers, json={"answers": {}}).status_code == 409

    with TestClient(app()) as restarted_again:
        assert restarted_again.get(path, headers=headers).json() == result

    stored = PostgresAttemptStore(bank).get(attempt_id)
    assert stored["answers"] == expected_answers and stored["raw_score"] == 10
    assert stored["result"] == result["result"]
    assert stored["token_hash"] == hashlib.sha256(attempt["attempt_token"].encode()).hexdigest()
    assert attempt["attempt_token"] not in str(stored)
    with psycopg.connect(bank.database_url) as connection:
        rows = connection.execute(
            "SELECT question_id,response,is_correct FROM practice_answer WHERE attempt_id=%s", (attempt_id,)
        ).fetchall()
    assert len(rows) == 10
    assert {str(question_id): response for question_id, response, _correct in rows} == expected_answers
    assert all(correct is True for _question_id, _response, correct in rows)
