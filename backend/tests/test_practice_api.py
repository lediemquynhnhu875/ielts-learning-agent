"""Reading/Listening HTTP lifecycle against transactional in-memory storage."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
import json
import threading
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from ielts_agent.api.main import create_app
from ielts_agent.core.config import Settings
from tests.test_api import AUTH, TOKEN, ApiBank
from tests.test_pipeline import FakeAgents


def practice_source(skill="reading"):
    item_id = str(uuid4())
    kinds = ["true_false_not_given", "multiple_choice", "sentence_completion", "matching_headings"]
    keys = ["TRUE", "A", "young trees", "ii", "FALSE", "B", "water quality", "iii"]
    groups, answers = [], []
    for position, kind in enumerate(kinds, 1):
        options = {"A": "Coastal forests", "B": "Railways", "C": "Factories"} if kind == "multiple_choice" else {}
        if kind == "matching_headings":
            options = {"i": "Urban development", "ii": "Restoration work", "iii": "Research"}
        group = {
            "group_id": str(uuid4()), "position": position, "question_type": kind,
            "instructions": "Answer each question.", "response_mode": "text" if kind == "sentence_completion" else "options",
            "options": options, "response_limits": {"max_words": 2} if kind == "sentence_completion" else {},
            "allow_reuse": False, "questions": [],
            "answer_key": "PRIVATE_GROUP_KEY",
        }
        for offset in range(2):
            number = position * 2 - 1 + offset
            question_id = str(uuid4())
            key = keys[position - 1 + 4 * offset]
            group["questions"].append({
                "id": question_id, "number": number, "position": offset + 1,
                "prompt": f"Question {number}", "options": {}, "target": {"evidence_span": "PRIVATE_TARGET_KEY"}, "excluded": False,
                "answer_key": "PRIVATE_QUESTION_KEY", "explanation": "PRIVATE_QUESTION_EXPLANATION",
            })
            answers.append({"question_id": question_id, "number": number, "answer_key": key,
                            "evidence_span": "Workers plant young trees.", "explanation": "The text gives the answer."})
        groups.append(group)
    exercise = {
        "id": item_id, "title": "Restoring coastal habitat", "text": "Workers plant young trees. Scientists measure water quality.",
        "skill": skill, "topic": "Conservation", "target_band": 6.0, "status": "verified",
        "source": "llm_generated_verified", "validation": {"rules": True, "solver": True},
        "trace_id": str(uuid4()), "model": "PRIVATE_MODEL", "prompt_version": "PRIVATE_PROMPT",
        "question_groups": groups,
    }
    return exercise, {"item_id": item_id, "answers": answers}


class MemoryAttemptStore:
    """Commit edits on success only, holding a lock for the complete operation."""

    def __init__(self, skill="reading"):
        self.source = practice_source(skill)
        self.records = {}
        self.lock = threading.RLock()

    def load_source(self, item_id):
        if self.source is None or self.source[0]["id"] != item_id:
            return None
        if self.source[0].get("status") != "verified":
            return None
        return deepcopy(self.source)

    def create(self, record):
        with self.lock:
            self.records[record["attempt_id"]] = deepcopy(record)

    def get(self, attempt_id):
        with self.lock:
            return deepcopy(self.records.get(attempt_id))

    @contextmanager
    def edit(self, attempt_id):
        with self.lock:
            record = deepcopy(self.records.get(attempt_id))
            yield record
            if record is not None:
                self.records[attempt_id] = deepcopy(record)


@pytest.fixture
def practice_api():
    store, agents, bank = MemoryAttemptStore(), FakeAgents([]), ApiBank()
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=bank, agents=agents, attempt_store=store)) as client:
        yield client, store, agents


def start(client, store):
    response = client.post(f"/api/exercises/{store.source[0]['id']}/attempts", headers=AUTH)
    assert response.status_code == 201, response.text
    assert response.headers["Cache-Control"] == "no-store"
    attempt = response.json()
    headers = {**AUTH, "X-Attempt-Token": attempt["attempt_token"]}
    return attempt, headers


def assert_private_until_submit(payload):
    hidden = {"answer_key", "evidence_span", "explanation", "trace_id", "model", "solver_model", "prompt_version", "token_hash", "answer_key_snapshot"}

    def check(value):
        if isinstance(value, dict):
            assert not hidden.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(payload)
    assert "PRIVATE_MODEL" not in str(payload) and "PRIVATE_PROMPT" not in str(payload)


def test_create_and_resume_private_persisted_attempt(practice_api):
    client, store, agents = practice_api
    attempt, headers = start(client, store)
    assert attempt["item_id"] == store.source[0]["id"]
    assert attempt["skill"] == "reading" and attempt["status"] == "in_progress"
    assert attempt["answers"] == {} and attempt["result"] is None and attempt["submitted_at"] is None
    assert attempt["elapsed_seconds"] >= 0
    assert datetime.fromisoformat(attempt["started_at"]).tzinfo is not None
    assert len(attempt["attempt_token"]) >= 32
    stored = store.get(attempt["attempt_id"])
    assert stored["token_hash"] != attempt["attempt_token"]
    assert attempt["attempt_token"] not in str(stored)
    assert_private_until_submit(attempt)
    resumed = client.get(f"/api/attempts/{attempt['attempt_id']}", headers=headers)
    assert resumed.status_code == 200
    assert resumed.headers["Cache-Control"] == "no-store"
    assert "attempt_token" not in resumed.json()
    assert resumed.json()["exercise"] == attempt["exercise"]
    assert_private_until_submit(resumed.json())
    assert agents.generate_calls == agents.solve_calls == 0 and not agents.safety_calls


@pytest.mark.parametrize("operation", ["get", "save", "submit"])
@pytest.mark.parametrize("token", [None, "wrong-secret"])
def test_attempt_access_requires_own_token(practice_api, operation, token):
    client, store, _ = practice_api
    attempt, _ = start(client, store)
    headers = dict(AUTH)
    if token is not None:
        headers["X-Attempt-Token"] = token
    path = f"/api/attempts/{attempt['attempt_id']}"
    response = client.get(path, headers=headers) if operation == "get" else (
        client.patch(path + "/answers", headers=headers, json={"answers": {}}) if operation == "save" else
        client.post(path + "/submit", headers=headers)
    )
    assert response.status_code == 404
    assert store.get(attempt["attempt_id"])["status"] == "in_progress"


def test_tokens_are_isolated_between_attempts(practice_api):
    client, store, _ = practice_api
    first, _ = start(client, store)
    second, second_headers = start(client, store)
    assert first["attempt_token"] != second["attempt_token"]
    assert client.get(f"/api/attempts/{first['attempt_id']}", headers=second_headers).status_code == 404


@pytest.mark.parametrize("operation", ["create", "get", "save", "submit"])
def test_shared_bearer_authentication_still_applies(practice_api, operation):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    headers.pop("Authorization")
    path = f"/api/attempts/{attempt['attempt_id']}"
    if operation == "create":
        response = client.post(f"/api/exercises/{store.source[0]['id']}/attempts", headers=headers)
    elif operation == "get":
        response = client.get(path, headers=headers)
    elif operation == "save":
        response = client.patch(path + "/answers", headers=headers, json={"answers": {}})
    else:
        response = client.post(path + "/submit", headers=headers)
    assert response.status_code == 401


def test_unknown_and_malformed_identifiers(practice_api):
    client, _, _ = practice_api
    assert client.post(f"/api/exercises/{uuid4()}/attempts", headers=AUTH).status_code == 404
    assert client.post("/api/exercises/invalid-id/attempts", headers=AUTH).status_code == 422
    assert client.get(f"/api/attempts/{uuid4()}", headers=AUTH).status_code == 404
    assert client.get("/api/attempts/invalid-id", headers=AUTH).status_code == 422


def test_unavailable_exercise_does_not_start_attempt(practice_api):
    client, store, _ = practice_api
    store.source[0]["status"] = "rejected"
    response = client.post(f"/api/exercises/{store.source[0]['id']}/attempts", headers=AUTH)
    assert response.status_code == 404 and not store.records


@pytest.mark.parametrize("defect", ["unsupported_skill", "excluded_question", "missing_key", "unsupported_type", "failed_validation"])
def test_ungradable_snapshot_is_rejected_without_partial_attempt(practice_api, defect):
    client, store, _ = practice_api
    exercise, key = store.source
    if defect == "unsupported_skill":
        exercise["skill"] = "writing"
    elif defect == "excluded_question":
        exercise["question_groups"][0]["questions"][0]["excluded"] = True
    elif defect == "missing_key":
        key["answers"].pop()
    elif defect == "unsupported_type":
        exercise["question_groups"][0]["question_type"] = "choose_two"
    else:
        exercise["validation"]["solver"] = False
    response = client.post(f"/api/exercises/{exercise['id']}/attempts", headers=AUTH)
    assert response.status_code == 409, response.text
    assert not store.records


def test_save_merges_and_clears_answers_with_canonical_question_ids(practice_api):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    first, second = [answer["question_id"] for answer in store.source[1]["answers"][:2]]
    path = f"/api/attempts/{attempt['attempt_id']}/answers"
    response = client.patch(path, headers=headers, json={"answers": {first.upper(): "true", second: "false"}})
    assert response.status_code == 200, response.text
    assert response.json()["answers"] == {first: "true", second: "false"}
    assert_private_until_submit(response.json())
    response = client.patch(path, headers=headers, json={"answers": {first: None}})
    assert response.status_code == 200
    assert response.json()["answers"] == {first: "", second: "false"}
    assert "attempt_token" not in response.json()
    response = client.patch(path, headers=headers, json={"answers": {second: " \t\n "}})
    assert response.status_code == 200 and response.json()["answers"] == {first: "", second: ""}


@pytest.mark.parametrize("bad_value", [42, False, [], {}, "a" * 2001])
def test_malformed_answer_values_fail_without_saving(practice_api, bad_value):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    question_id = store.source[1]["answers"][0]["question_id"]
    response = client.patch(f"/api/attempts/{attempt['attempt_id']}/answers", headers=headers,
                            json={"answers": {question_id: bad_value}})
    assert response.status_code == 422
    assert store.get(attempt["attempt_id"])["answers"] == {}


@pytest.mark.parametrize("payload", [
    {"answers": {"invalid-id": "a"}},
    {"answers": {}, "score": 8},
    {"answers": {str(uuid4()): "A" for _ in range(41)}},
])
def test_invalid_answer_payload_is_rejected(practice_api, payload):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    response = client.patch(f"/api/attempts/{attempt['attempt_id']}/answers", headers=headers, json=payload)
    assert response.status_code == 422
    assert store.get(attempt["attempt_id"])["answers"] == {}


def test_duplicate_uuid_aliases_and_oversized_token_are_rejected(practice_api):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    question_id = store.source[1]["answers"][0]["question_id"]
    response = client.patch(f"/api/attempts/{attempt['attempt_id']}/answers", headers=headers,
                            json={"answers": {question_id: "TRUE", "{" + question_id + "}": "FALSE"}})
    assert response.status_code == 422
    assert store.get(attempt["attempt_id"])["answers"] == {}
    response = client.get(f"/api/attempts/{attempt['attempt_id']}", headers={**AUTH, "X-Attempt-Token": "a" * 257})
    assert response.status_code == 422


@pytest.mark.parametrize("operation", ["save", "submit"])
@pytest.mark.parametrize("bad_value", ["bad\x00text", "\ud800", "\ud800\x00", "\ud800" + "a" * 2001],
                         ids=["nul", "unpaired-surrogate", "surrogate-and-nul", "surrogate-and-overlong"])
def test_unstorable_unicode_is_rejected_without_partially_saving(practice_api, operation, bad_value):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    first, second = [answer["question_id"] for answer in store.source[1]["answers"][:2]]
    payload = json.dumps({"answers": {first: "TRUE", second: bad_value}}).encode("ascii")
    path = f"/api/attempts/{attempt['attempt_id']}"
    response = client.request("PATCH" if operation == "save" else "POST",
                              path + ("/answers" if operation == "save" else "/submit"),
                              headers={**headers, "Content-Type": "application/json"}, content=payload)
    assert response.status_code == 422, response.text
    assert response.headers["Cache-Control"] == "no-store"
    saved = store.get(attempt["attempt_id"])
    assert saved["answers"] == {} and saved["status"] == "in_progress" and saved["result"] is None
    error = response.json()
    if "detail" in error:
        assert all(set(issue) <= {"type", "loc", "msg"} for issue in error["detail"])
    else:
        assert error["error"] == "invalid_answer"


@pytest.mark.parametrize("operation", ["save", "submit"])
def test_foreign_question_rejects_entire_update(practice_api, operation):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    question_id = store.source[1]["answers"][0]["question_id"]
    payload = {"answers": {question_id: "TRUE", str(uuid4()): "foreign"}}
    path = f"/api/attempts/{attempt['attempt_id']}"
    response = client.patch(path + "/answers", headers=headers, json=payload) if operation == "save" else client.post(path + "/submit", headers=headers, json=payload)
    assert response.status_code == 422
    saved = store.get(attempt["attempt_id"])
    assert saved["answers"] == {} and saved["status"] == "in_progress" and saved["result"] is None


def test_saved_answers_submit_without_request_body_and_lock_result(practice_api):
    client, store, agents = practice_api
    attempt, headers = start(client, store)
    answers = {answer["question_id"]: answer["answer_key"] for answer in store.source[1]["answers"]}
    path = f"/api/attempts/{attempt['attempt_id']}"
    assert client.patch(path + "/answers", headers=headers, json={"answers": answers}).status_code == 200
    response = client.post(path + "/submit", headers=headers)
    assert response.status_code == 200, response.text
    submitted = response.json()
    assert submitted["status"] == "submitted" and submitted["submitted_at"] is not None
    assert submitted["answers"] == answers and submitted["result"]["raw_score"] == 8
    assert "attempt_token" not in submitted
    result = submitted["result"]
    assert result["band"] is None and result["band_reason"] == "partial_practice"
    assert result["percentage"] == 100 and result["total_questions"] == 8
    assert result["answered_questions"] == 8 and result["unanswered_count"] == result["wrong_count"] == 0
    assert result["grading_version"] == "fixed-key-v1"
    assert len(result["questions"]) == 8 and all(question["is_correct"] for question in result["questions"])
    assert {question["question_id"]: question["correct_answer"] for question in result["questions"]} == answers
    assert all(question["explanation"] and question["evidence_span"] for question in result["questions"])
    retry = client.post(path + "/submit", headers=headers, json={"answers": {key: "wrong" for key in answers}})
    assert retry.status_code == 200 and retry.json()["result"] == submitted["result"]
    assert retry.json()["answers"] == submitted["answers"]
    assert retry.json()["submitted_at"] == submitted["submitted_at"]
    assert client.patch(path + "/answers", headers=headers, json={"answers": {next(iter(answers)): "wrong"}}).status_code == 409
    assert client.get(path, headers=headers).json()["result"] == submitted["result"]
    assert agents.generate_calls == agents.solve_calls == 0 and not agents.safety_calls


def test_submit_applies_final_answer_patch_and_counts_unanswered_wrong(practice_api):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    first, second = store.source[1]["answers"][:2]
    path = f"/api/attempts/{attempt['attempt_id']}"
    client.patch(path + "/answers", headers=headers, json={"answers": {first["question_id"]: "wrong"}})
    response = client.post(path + "/submit", headers=headers,
                           json={"answers": {first["question_id"]: first["answer_key"], second["question_id"]: second["answer_key"]}})
    assert response.status_code == 200, response.text
    assert response.json()["result"]["raw_score"] == 2
    assert response.json()["result"]["percentage"] == 25
    assert response.json()["result"]["unanswered_count"] == 6


def test_empty_submit_scores_zero(practice_api):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    response = client.post(f"/api/attempts/{attempt['attempt_id']}/submit", headers=headers)
    assert response.status_code == 200
    assert response.json()["result"]["raw_score"] == 0
    assert response.json()["result"]["percentage"] == 0
    assert all(question["reason"] == "unanswered" for question in response.json()["result"]["questions"])


def test_listening_uses_same_deterministic_submission_flow():
    store, agents = MemoryAttemptStore("listening"), FakeAgents([])
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=ApiBank(), agents=agents, attempt_store=store)) as client:
        attempt, headers = start(client, store)
        assert attempt["skill"] == "listening"
        assert attempt["exercise"]["text"] == store.source[0]["text"]
        answers = {answer["question_id"]: answer["answer_key"].upper() for answer in store.source[1]["answers"]}
        response = client.post(f"/api/attempts/{attempt['attempt_id']}/submit", headers=headers, json={"answers": answers})
        assert response.status_code == 200, response.text
        assert response.json()["result"]["raw_score"] == 8
        assert response.json()["result"]["band"] is None
    assert agents.generate_calls == agents.solve_calls == 0


def test_snapshot_survives_source_mutation_and_new_app_instance(practice_api):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    correct = {answer["question_id"]: answer["answer_key"] for answer in store.source[1]["answers"]}
    original_text = attempt["exercise"]["text"]
    store.source[0]["text"] = "Changed after this attempt started."
    for answer in store.source[1]["answers"]:
        answer["answer_key"] = "mutated"
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=ApiBank(), agents=FakeAgents([]), attempt_store=store)) as restarted:
        path = f"/api/attempts/{attempt['attempt_id']}"
        assert restarted.get(path, headers=headers).json()["exercise"]["text"] == original_text
        response = restarted.post(path + "/submit", headers=headers, json={"answers": correct})
        assert response.status_code == 200 and response.json()["result"]["raw_score"] == 8


def test_concurrent_submissions_publish_one_immutable_result(practice_api):
    client, store, _ = practice_api
    attempt, headers = start(client, store)
    correct = {answer["question_id"]: answer["answer_key"] for answer in store.source[1]["answers"]}
    barrier = threading.Barrier(2)

    def submit(responses):
        barrier.wait(timeout=10)
        return client.post(f"/api/attempts/{attempt['attempt_id']}/submit", headers=headers, json={"answers": responses})

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(submit, correct)
        second = pool.submit(submit, {question: "wrong" for question in correct})
        responses = [first.result(timeout=15), second.result(timeout=15)]
    assert all(response.status_code == 200 for response in responses)
    left, right = [response.json() for response in responses]
    assert left["result"] == right["result"] and left["answers"] == right["answers"]
    assert left["submitted_at"] == right["submitted_at"]
    assert left["result"]["raw_score"] in (0, 8)
