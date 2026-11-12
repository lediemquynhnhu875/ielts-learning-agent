"""Database integration tests use an isolated PostgreSQL schema per test.

Set TEST_DATABASE_URL to run them. Tests never clear the shared public schema.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
import threading
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from ielts_agent.infrastructure.db.bank import Bank, DuplicateError, _cosine, _terms
from ielts_agent.agents.uc04.models import ExerciseDraft, GenerateRequest
from ielts_agent.agents.uc04.rules import word_count


def _request():
    return GenerateRequest(skill="reading", topic="Can Gio mangroves", target_band=6)


def _draft(filler="habitat"):
    text = "The reserve protects coastal forests. Workers plant young trees. "
    text += " ".join([filler] * (650 - word_count(text)))
    questions = []
    for index in range(10):
        kind = "true_false_not_given" if index < 3 else "multiple_choice" if index < 6 else "sentence_completion"
        questions.append({
            "id": f"q{index + 1}", "kind": kind,
            "prompt": "Workers plant ____ in the reserve." if kind == "sentence_completion" else "The reserve protects coastal forests.",
            "options": {"A": "Coastal forests", "B": "Urban railways", "C": "Factories"} if kind == "multiple_choice" else {},
            "word_limit": 2 if kind == "sentence_completion" else None,
            "answer": "young trees" if kind == "sentence_completion" else "A" if kind == "multiple_choice" else "TRUE",
            "evidence_span": "Workers plant young trees." if kind == "sentence_completion" else "The reserve protects coastal forests.",
            "explanation": "The evidence explicitly gives the answer.",
        })
    return ExerciseDraft(title="Mangroves", text=text, questions=questions)


def _metadata():
    return {"model": "test-generator", "prompt_version": "generation-v1", "solver_model": "test-solver",
            "solver_prompt_version": "solver-v1", "skill_hash": "test-sha256"}


def _trace(draft):
    return {"id": str(uuid4()), "status": "running", "attempts": [{
        "rules": {"exercise_errors": [], "items": {q.id: [] for q in draft.questions}},
        "solver": {"status": "passed", "items": {q.id: {
            "passed": True, "reasons": [], "answer": q.answer, "evidence_span": q.evidence_span,
        } for q in draft.questions}},
    }]}


@pytest.fixture
def bank():
    base_url = os.getenv("TEST_DATABASE_URL")
    if not base_url:
        pytest.skip("Set TEST_DATABASE_URL to run isolated PostgreSQL integration tests")
    schema = "uc04_test_" + uuid4().hex
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query))
    query["options"] = f"-csearch_path={schema}"
    scoped_url = urlunsplit(parts._replace(query=urlencode(query)))
    instance = Bank(scoped_url)
    try:
        instance.initialize()
        yield instance
    finally:
        # The UUID-named schema was created by this fixture; public is untouched.
        assert schema.startswith("uc04_test_") and len(schema) == 42
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_unicode_casefold_cosine():
    assert _cosine(_terms("CẦN GIỜ Trees trees"), _terms("cần giờ trees TREES")) == pytest.approx(1)
    assert _cosine(_terms("cần giờ"), _terms("cần giờ")) == pytest.approx(1)
    assert _cosine(_terms("mangroves"), _terms("railways")) == 0
    assert _cosine(_terms(""), _terms("railways")) == 0


@pytest.mark.parametrize("layer", ["rules", "solver", "missing_rules", "missing_solver", "wrong_solver_status", "missing_metadata"])
def test_unverified_trace_rejected_without_touching_database(layer):
    draft, metadata = _draft(), _metadata()
    trace = _trace(draft)
    final = trace["attempts"][-1]
    if layer == "rules":
        final["rules"]["items"]["q1"] = ["wrong evidence"]
    elif layer == "solver":
        final["solver"]["items"]["q1"]["passed"] = False
    elif layer == "missing_rules":
        del final["rules"]["items"]["q1"]
    elif layer == "missing_solver":
        del final["solver"]["items"]["q1"]
    elif layer == "wrong_solver_status":
        final["solver"]["status"] = "failed"
    else:
        del metadata["solver_model"]
    with pytest.raises(ValueError):
        Bank("postgresql://unused/unused").save_verified(_request(), draft, metadata, trace)


def test_rechecks_rules_even_if_trace_claims_success():
    draft = _draft()
    trace = _trace(draft)
    draft.questions[6].answer = "plant young trees"
    with pytest.raises(ValueError, match="publication rule"):
        Bank("postgresql://unused/unused").save_verified(_request(), draft, _metadata(), trace)


@pytest.mark.parametrize("missing_or_failed_layer", ["rules", "solver", "dedup"])
def test_retrieval_requires_recorded_passing_validation(missing_or_failed_layer):
    class Cursor:
        def fetchone(self):
            return {"item_id": str(uuid4())}

        def fetchall(self):
            return [{"layer": layer, "passed": layer != missing_or_failed_layer}
                    for layer in ("rules", "solver", "dedup")]

    class Connection:
        def execute(self, query, params):
            return Cursor()

    # No network connection: a row's verified status alone must never authorize
    # returning content when a recorded validator did not pass.
    assert Bank._readable_item(Connection(), str(uuid4())) is None


def test_normalized_groups_public_projection_and_answer_separation(bank):
    draft = _draft()
    trace = _trace(draft)
    result = bank.save_verified(_request(), draft, _metadata(), trace)
    assert result == bank.get_item(result["id"])
    assert result["source"] == "llm_generated_verified"
    assert result["validation"] == {"rules": True, "solver": True}
    groups = result["question_groups"]
    assert [group["position"] for group in groups] == [1, 2, 3]
    assert [len(group["questions"]) for group in groups] == [3, 3, 4]
    assert groups[1]["options"] == draft.questions[3].options
    assert groups[2]["response_limits"] == {"max_words": 2}
    questions = [q for group in groups for q in group["questions"]]
    assert [q["number"] for q in questions] == list(range(1, 11))
    assert all(q["options"] == {} for q in questions)

    def check_public(value):
        if isinstance(value, dict):
            assert not {"answer", "answer_key", "evidence_span", "explanation"} & value.keys()
            for child in value.values():
                check_public(child)
        elif isinstance(value, list):
            for child in value:
                check_public(child)

    check_public(result)
    answers = bank.get_answers(result["id"])
    assert [answer["answer_key"] for answer in answers["answers"]] == [q.answer for q in draft.questions]
    assert [answer["question_id"] for answer in answers["answers"]] == [q["id"] for q in questions]
    with psycopg.connect(bank.database_url, row_factory=psycopg.rows.dict_row) as connection:
        body = connection.execute("SELECT body,question_type FROM content_item").fetchone()
        assert set(body["body"]) == {"title", "text", "metadata", "trace_id"}
        assert body["question_type"] is None
        assert connection.execute("SELECT count(*) AS count FROM question WHERE question_type IS NOT NULL").fetchone()["count"] == 0
        layers = connection.execute("SELECT layer,count(*) AS count FROM validation_result GROUP BY layer").fetchall()
        assert {row["layer"]: row["count"] for row in layers} == {"rules": 11, "solver": 11, "dedup": 1}
    saved_trace = bank.get_trace(trace["id"])
    assert saved_trace == trace
    assert saved_trace["status"] == "verified" and saved_trace["item_id"] == result["id"]


def test_exact_duplicate_is_rejected_without_partial_write(bank):
    draft = _draft()
    first_trace = _trace(draft)
    first = bank.save_verified(_request(), draft, _metadata(), first_trace)
    second_trace = _trace(draft)
    original = deepcopy(second_trace)
    with pytest.raises(DuplicateError) as error:
        bank.save_verified(_request(), draft, _metadata(), second_trace)
    assert error.value.similarity == pytest.approx(1)
    assert error.value.item_id == first["id"]
    assert second_trace == original
    assert bank.get_trace(second_trace["id"]) is None
    with psycopg.connect(bank.database_url) as connection:
        assert connection.execute("SELECT count(*) FROM content_item").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM question").fetchone()[0] == 10


def test_concurrent_duplicate_publication_is_atomic(bank):
    barrier = threading.Barrier(2)

    def publish():
        draft = _draft()
        barrier.wait(timeout=10)
        try:
            return bank.save_verified(_request(), draft, _metadata(), _trace(draft))["id"]
        except DuplicateError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: publish(), range(2)))
    assert results.count("duplicate") == 1
    with psycopg.connect(bank.database_url) as connection:
        assert connection.execute("SELECT count(*) FROM content_item").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM uc04_trace").fetchone()[0] == 1


def test_database_parent_and_position_constraints(bank):
    first_draft, second_draft = _draft(), _draft("railway")
    first = bank.save_verified(_request(), first_draft, _metadata(), _trace(first_draft))
    second = bank.save_verified(_request(), second_draft, _metadata(), _trace(second_draft))
    question_id = first["question_groups"][0]["questions"][0]["id"]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with psycopg.connect(bank.database_url) as connection:
            # An unused number isolates the parent FK from the destination
            # item's existing (item_id, number=1) uniqueness constraint.
            connection.execute("UPDATE question SET item_id=%s, number=40 WHERE id=%s", (second["id"], question_id))
    with pytest.raises(psycopg.errors.UniqueViolation):
        with psycopg.connect(bank.database_url) as connection:
            connection.execute("UPDATE question_group SET position=1 WHERE group_id=%s", (first["question_groups"][1]["group_id"],))
    with pytest.raises(psycopg.errors.UniqueViolation):
        with psycopg.connect(bank.database_url) as connection:
            connection.execute("UPDATE question SET number=1 WHERE id=%s", (first["question_groups"][1]["questions"][0]["id"],))


def test_failed_trace_and_missing_items(bank):
    trace = {"id": str(uuid4()), "status": "failed", "attempts": []}
    bank.save_trace(trace)
    trace["reason"] = "provider unavailable"
    bank.save_trace(trace)
    assert bank.get_trace(trace["id"]) == trace
    assert bank.get_item(str(uuid4())) is None
    assert bank.get_answers(str(uuid4())) is None
    assert bank.get_item("invalid-id") is None
    assert bank.get_answers("invalid-id") is None


@pytest.mark.parametrize("invalidation", ["excluded", "rejected", "spare", "failed_validation"])
def test_invalidated_content_and_answers_are_unavailable(bank, invalidation):
    draft = _draft()
    item = bank.save_verified(_request(), draft, _metadata(), _trace(draft))
    with psycopg.connect(bank.database_url) as connection:
        if invalidation == "excluded":
            question_id = item["question_groups"][0]["questions"][0]["id"]
            connection.execute("UPDATE question SET excluded=true WHERE id=%s", (question_id,))
        elif invalidation == "failed_validation":
            connection.execute("UPDATE validation_result SET passed=false WHERE item_id=%s AND layer='solver' AND question_id IS NOT NULL", (item["id"],))
        else:
            connection.execute("UPDATE content_item SET status=%s WHERE item_id=%s", (invalidation, item["id"]))
    assert bank.get_item(item["id"]) is None
    assert bank.get_answers(item["id"]) is None


def _listing_item(bank, filler, *, title="Mangroves", topic="Can Gio mangroves", skill="reading", target_band=6):
    draft = _draft(filler)
    draft.title = title
    request = GenerateRequest(skill="reading", topic=topic, target_band=target_band)
    item = bank.save_verified(request, draft, _metadata(), _trace(draft))
    if skill != "reading":
        # Exercise SQL listing across skills without invoking a generation model.
        with psycopg.connect(bank.database_url) as connection:
            connection.execute("UPDATE content_item SET skill=%s WHERE item_id=%s", (skill.title(), item["id"]))
    return item


def test_listing_empty_bank_and_offset_beyond_last_page(bank):
    assert bank.list_items() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    _listing_item(bank, "habitat")
    assert bank.list_items(limit=2, offset=100) == {"items": [], "total": 1, "limit": 2, "offset": 100}
    assert bank.list_items(q="missing") == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_listing_summaries_counts_types_and_deterministic_pagination(bank):
    first = _listing_item(bank, "habitat", title="First reserve")
    second = _listing_item(bank, "railway", title="Second reserve")
    third = _listing_item(bank, "wetland", title="Newest reserve")
    with psycopg.connect(bank.database_url) as connection:
        connection.execute("UPDATE content_item SET created_at='2026-11-10T00:00:00Z'")
        connection.execute("UPDATE content_item SET created_at='2026-11-11T00:00:00Z' WHERE item_id=%s", (third["id"],))
    expected_ids = [third["id"], *sorted([first["id"], second["id"]], reverse=True)]
    result = bank.list_items(limit=2)
    assert result["total"] == 3
    assert [item["id"] for item in result["items"]] == expected_ids[:2]
    item = result["items"][0]
    assert set(item) == {
        "id", "title", "skill", "topic", "target_band", "source", "status",
        "created_at", "question_count", "question_types",
    }
    assert item["question_count"] == 10
    assert item["question_types"] == ["multiple_choice", "sentence_completion", "true_false_not_given"]
    page_two = bank.list_items(limit=2, offset=2)
    assert page_two["total"] == 3 and [item["id"] for item in page_two["items"]] == expected_ids[2:]


def test_listing_filters_skill_band_and_literal_title_or_topic_substring(bank):
    reading = _listing_item(bank, "habitat", title="Reserve 100%_Complete", target_band=6)
    listening = _listing_item(bank, "railway", title="Transport briefing", topic="Urban Railways", skill="listening", target_band=6.5)
    _listing_item(bank, "wetland", title="Reserve 100XComplete", target_band=7)
    for query, expected_id in [("100%_", reading["id"]), ("100%", reading["id"]), ("_complete", reading["id"]),
                               ("RESERVE 100%", reading["id"]), ("rAiLwAyS", listening["id"])]:
        result = bank.list_items(q=query)
        assert result["total"] == 1 and [item["id"] for item in result["items"]] == [expected_id]
    result = bank.list_items(skill="listening", target_band=6.5, q="URBAN")
    assert result["total"] == 1 and result["items"][0]["id"] == listening["id"]
    assert bank.list_items(skill="reading", target_band=6.5)["total"] == 0
    assert bank.list_items(q="%' OR true --")["total"] == 0


@pytest.mark.parametrize("invalidation", [
    "excluded", "rejected", "spare", "writing", "speaking",
    "failed_rules", "failed_solver", "failed_dedup", "missing_rules", "missing_solver", "missing_dedup",
])
def test_listing_never_exposes_unavailable_or_other_skill_content(bank, invalidation):
    item = _listing_item(bank, "habitat")
    with psycopg.connect(bank.database_url) as connection:
        if invalidation == "excluded":
            connection.execute("UPDATE question SET excluded=true WHERE id=%s", (item["question_groups"][0]["questions"][0]["id"],))
        elif invalidation in ("rejected", "spare"):
            connection.execute("UPDATE content_item SET status=%s WHERE item_id=%s", (invalidation, item["id"]))
        elif invalidation in ("writing", "speaking"):
            connection.execute("UPDATE content_item SET skill=%s WHERE item_id=%s", (invalidation.title(), item["id"]))
        elif invalidation.startswith("failed_"):
            layer = invalidation.removeprefix("failed_")
            # Keep passing siblings: BOOL_OR or a status-only gate would leak it.
            connection.execute("UPDATE validation_result SET passed=false WHERE id=(SELECT id FROM validation_result WHERE item_id=%s AND layer=%s LIMIT 1)", (item["id"], layer))
        else:
            connection.execute("DELETE FROM validation_result WHERE item_id=%s AND layer=%s", (item["id"], invalidation.removeprefix("missing_")))
    result = bank.list_items()
    assert result["total"] == 0 and result["items"] == []
