"""HTTP adapter tests with fake agents/storage: no network, database or keys."""

from copy import deepcopy
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest

from ielts_agent.api.main import create_app
from ielts_agent.core.config import Settings
from ielts_agent.core.errors import ProviderError
from ielts_agent.infrastructure.db.bank import BankNotInitializedError
from tests.test_pipeline import FakeAgents, RecordingBank, practice_draft, practice_request


TOKEN = "offline-test-api-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class ApiBank(RecordingBank):
    """Fixed storage projection lets adapter tests check forwarding independently."""

    def __init__(self):
        super().__init__()
        self.list_calls = []
        self.item_id = str(uuid4())
        self.question_id = str(uuid4())
        self.item = {
            "id": self.item_id, "title": "An offline reserve", "text": "Public passage.",
            "source": "llm_generated_verified", "status": "verified",
            "validation": {"rules": True, "solver": True},
            "question_groups": [{"group_id": str(uuid4()), "position": 1,
                                 "question_type": "true_false_not_given", "questions": [{
                                     "id": self.question_id, "number": 1, "position": 1,
                                     "prompt": "The reserve protects forests.", "excluded": False,
                                 }]}],
        }
        self.answers = {"item_id": self.item_id, "answers": [{
            "question_id": self.question_id, "number": 1, "answer_key": "TRUE",
            "evidence_span": "The reserve protects forests.", "explanation": "The text states it.",
        }]}

    def initialize(self):
        """The offline fake has no PostgreSQL schema to migrate at startup."""

    def save_verified(self, request, draft, metadata, trace):
        super().save_verified(request, draft, metadata, trace)
        trace["item_id"] = self.item_id
        self.item["trace_id"] = trace["id"]
        self.save_trace(trace)
        return deepcopy(self.item)

    def get_item(self, item_id):
        return deepcopy(self.item) if item_id == self.item_id else None

    def get_answers(self, item_id):
        return deepcopy(self.answers) if item_id == self.item_id else None

    def list_items(self, **filters):
        self.list_calls.append(filters)
        return {"items": [{
            "id": self.item_id, "title": "An offline reserve", "skill": "reading",
            "topic": "Coastal forests", "target_band": 6,
            "source": "llm_generated_verified", "status": "verified",
            "created_at": "2026-11-11T08:00:00+00:00", "question_count": 10,
            "question_types": ["multiple_choice", "sentence_completion", "true_false_not_given"],
        }], "total": 1, "limit": filters["limit"], "offset": filters["offset"]}


@pytest.fixture
def api():
    bank = ApiBank()
    agents = FakeAgents([practice_draft()])
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=bank, agents=agents)) as client:
        yield client, bank, agents


def test_generation_and_read_routes_forward_hierarchical_public_content(api):
    client, bank, agents = api
    response = client.post("/api/exercises", json=practice_request().model_dump(), headers=AUTH)
    assert response.status_code == 201
    exercise = response.json()
    assert exercise == bank.item
    assert "question_groups" in exercise and "questions" not in exercise
    assert len(bank.saved) == 1 and agents.generate_calls == agents.solve_calls == 1
    assert client.get(f"/api/exercises/{bank.item_id}", headers=AUTH).json() == exercise
    answers = client.get(f"/api/exercises/{bank.item_id}/answers", headers=AUTH)
    assert answers.status_code == 200 and answers.json() == bank.answers
    assert "answer_key" not in str(exercise)
    trace = client.get(f"/api/traces/{exercise['trace_id']}", headers=AUTH)
    assert trace.status_code == 200
    assert trace.json()["status"] == "verified"
    assert trace.json()["item_id"] == bank.item_id


def test_list_exercises_returns_answer_free_summaries_with_defaults(api):
    client, bank, agents = api
    response = client.get("/api/exercises", headers=AUTH)
    assert response.status_code == 200
    result = response.json()
    assert {key: result[key] for key in ("total", "limit", "offset")} == {
        "total": 1, "limit": 20, "offset": 0,
    }
    assert result["items"][0]["id"] == bank.item_id
    assert set(result["items"][0]) == {
        "id", "title", "skill", "topic", "target_band", "source", "status",
        "created_at", "question_count", "question_types",
    }
    assert bank.list_calls == [{"skill": None, "target_band": None, "q": "", "limit": 20, "offset": 0}]
    assert agents.generate_calls == agents.solve_calls == 0 and not bank.saved


def test_list_exercises_forwards_validated_filters_and_trims_search(api):
    client, bank, _ = api
    response = client.get("/api/exercises", params={
        "skill": "listening", "target_band": "6.5", "q": "  CẦN GIỜ_%  ", "limit": 7, "offset": 14,
    }, headers=AUTH)
    assert response.status_code == 200
    assert bank.list_calls == [{
        "skill": "listening", "target_band": 6.5, "q": "CẦN GIỜ_%", "limit": 7, "offset": 14,
    }]


@pytest.mark.parametrize("params", [
    {"skill": "writing"}, {"skill": "Reading"}, {"target_band": "6.3"},
    {"target_band": "0.5"}, {"target_band": "9.5"}, {"target_band": "nan"},
    {"target_band": "inf"}, {"limit": 0}, {"limit": 101}, {"limit": "1.5"},
    {"offset": -1}, {"offset": "1.5"}, {"offset": 2147483648},
    {"q": "x" * 201}, {"q": "bad\x00query"},
])
def test_list_exercises_rejects_invalid_queries_before_storage(api, params):
    client, bank, _ = api
    response = client.get("/api/exercises", params=params, headers=AUTH)
    assert response.status_code == 422
    assert not bank.list_calls


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong-token"}])
def test_list_exercises_requires_bearer_before_storage(api, headers):
    client, bank, agents = api
    response = client.get("/api/exercises", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert not bank.list_calls and agents.generate_calls == 0


@pytest.mark.parametrize("error", [
    BankNotInitializedError("RAW_DATABASE_SECRET uninitialized"),
    psycopg.OperationalError("RAW_DATABASE_SECRET postgres password"),
])
def test_list_database_failures_return_sanitized_503(api, monkeypatch, error):
    client, bank, _ = api

    def unavailable(**filters):
        raise error

    monkeypatch.setattr(bank, "list_items", unavailable)
    response = client.get("/api/exercises", headers=AUTH)
    assert response.status_code == 503 and response.json()["error"] == "database_unavailable"
    assert "RAW_DATABASE_SECRET" not in response.text


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong-token"}])
@pytest.mark.parametrize("route", ["generate", "item", "answers", "trace"])
def test_protected_routes_reject_missing_or_wrong_bearer_before_work(api, headers, route):
    client, bank, agents = api
    if route == "generate":
        response = client.post("/api/exercises", json=practice_request().model_dump(), headers=headers)
    else:
        path = f"/api/traces/{uuid4()}" if route == "trace" else f"/api/exercises/{bank.item_id}"
        if route == "answers":
            path += "/answers"
        response = client.get(path, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert agents.generate_calls == agents.solve_calls == 0 and not bank.saved


def test_health_is_public_even_with_wrong_credentials(api):
    client, _, agents = api
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 200
    assert not agents.safety_calls


@pytest.mark.parametrize("updates", [
    {"target_band": 6.3}, {"target_band": 9.5}, {"question_count": 7},
    {"question_count": 14}, {"skill": "writing"}, {"completion_word_limit": 0},
])
def test_invalid_generation_requests_return_422_without_agent_work(api, updates):
    client, bank, agents = api
    payload = {**practice_request().model_dump(), **updates}
    assert client.post("/api/exercises", json=payload, headers=AUTH).status_code == 422
    assert agents.generate_calls == 0 and not bank.saved


@pytest.mark.parametrize("path", ["/api/exercises/{id}", "/api/exercises/{id}/answers", "/api/traces/{id}"])
def test_missing_resources_and_invalid_ids(api, path):
    client, _, _ = api
    assert client.get(path.format(id=uuid4()), headers=AUTH).status_code == 404
    assert client.get(path.format(id="invalid-id"), headers=AUTH).status_code == 422


def test_unsafe_topic_returns_400_and_preserves_failed_trace():
    bank = ApiBank()
    agents = FakeAgents([practice_draft()], safety_results=[False])
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=bank, agents=agents)) as client:
        response = client.post("/api/exercises", json=practice_request().model_dump(), headers=AUTH)
        assert response.status_code == 400 and response.json()["error"] == "unsafe_topic"
        trace = client.get(f"/api/traces/{response.json()['trace_id']}", headers=AUTH)
        assert trace.status_code == 200 and trace.json()["status"] == "unsafe_topic"
    assert agents.generate_calls == agents.solve_calls == 0 and not bank.saved


def test_provider_failure_returns_503_with_trace():
    bank = ApiBank()
    agents = FakeAgents([ProviderError("Sanitized provider failure")])
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=bank, agents=agents)) as client:
        response = client.post("/api/exercises", json=practice_request().model_dump(), headers=AUTH)
        assert response.status_code == 503 and response.json()["error"] == "provider_error"
        trace = client.get(f"/api/traces/{response.json()['trace_id']}", headers=AUTH)
        assert trace.json()["status"] == "provider_error"
    assert not bank.saved


@pytest.mark.parametrize("error", [
    BankNotInitializedError("RAW_DATABASE_SECRET uninitialized"),
    psycopg.OperationalError("RAW_DATABASE_SECRET postgres password"),
])
def test_database_failures_return_sanitized_503(error):
    class UnavailableBank(ApiBank):
        def get_item(self, item_id):
            raise error

    bank = UnavailableBank()
    agents = FakeAgents([practice_draft()])
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=bank, agents=agents)) as client:
        response = client.get(f"/api/exercises/{bank.item_id}", headers=AUTH)
    assert response.status_code == 503 and response.json()["error"] == "database_unavailable"
    assert "RAW_DATABASE_SECRET" not in response.text
