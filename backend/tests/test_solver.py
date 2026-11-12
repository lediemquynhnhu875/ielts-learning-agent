"""Independent solver payload, provider and evidence contracts, without storage."""

import json

import pytest

from ielts_agent.agents.uc04.models import ExerciseDraft, SolverAnswer, SolverOutput
from ielts_agent.agents.uc04.solver import BlindSolverAgent
from ielts_agent.agents.uc04.validation import validate_with_solver
from ielts_agent.core.config import Settings
from ielts_agent.core.errors import InvalidAgentOutput, ProviderError
from ielts_agent.infrastructure.llm.client import JsonLLMClient

from .test_generation import generation_payload


def solver_draft(skill="reading"):
    return ExerciseDraft.model_validate(generation_payload(skill))


def solver_output(draft):
    return SolverOutput(answers=[SolverAnswer(
        id=question.id, answer=question.answer, evidence_span=question.evidence_span,
        reason="The passage explicitly supplies this answer.",
    ) for question in draft.questions])


@pytest.mark.parametrize("skill", ["reading", "listening"])
def test_solver_receives_only_public_allowlist_without_generator_secrets(skill, harness_factory):
    draft = solver_draft(skill)
    independent = solver_output(draft)
    for question in draft.questions:
        question.answer = "GENERATOR_KEY_SECRET"
        question.evidence_span = "GENERATOR_EVIDENCE_SECRET"
        question.explanation = "GENERATOR_EXPLANATION_SECRET"
        question.__dict__["future_answer_field"] = "FUTURE_KEY_SECRET"
    harness = harness_factory(content=independent.model_dump())
    agent = BlindSolverAgent(JsonLLMClient(Settings(), "solver", client=harness.client))

    assert agent.run(draft) == independent

    body = harness.requests[0]["body"]
    payload = json.loads(body["messages"][1]["content"])
    assert set(payload) == {"text", "questions"}
    assert payload["text"] == draft.text
    expected = {"id", "kind", "prompt", "options", "word_limit", "paragraph_id"}
    assert len(payload["questions"]) == 10
    assert all(set(question) == expected for question in payload["questions"])
    wire = json.dumps(payload)
    for secret in ["GENERATOR_KEY_SECRET", "GENERATOR_EVIDENCE_SECRET",
                   "GENERATOR_EXPLANATION_SECRET", "FUTURE_KEY_SECRET"]:
        assert secret not in wire


@pytest.mark.parametrize("provider,token_key", [
    ("openai", "max_completion_tokens"), ("deepseek", "max_tokens"),
])
def test_solver_has_independent_model_transport_and_version_metadata(provider, token_key, harness_factory):
    draft = solver_draft()
    harness = harness_factory(content=solver_output(draft).model_dump())
    settings = Settings(provider="openai", generator_model="generator-model",
                        solver_provider=provider, solver_model="independent-model")
    agent = BlindSolverAgent(JsonLLMClient(settings, "solver", client=harness.client))
    agent.run(draft)
    agent.run(draft)

    first, second = [request["body"] for request in harness.requests]
    assert first["model"] == second["model"] == "independent-model"
    assert first[token_key] == 6144
    assert first["response_format"] == {"type": "json_object"}
    assert len(first["messages"]) == len(second["messages"]) == 2
    assert "generator-model" not in json.dumps(first)
    assert agent.metadata == {
        "solver_provider": provider, "solver_model": "independent-model",
        "solver_prompt_version": "blind-reading-solver.v1",
    }


@pytest.mark.parametrize("content", [
    "not JSON", "", None, {}, {"answers": "not a list"},
    {"answers": [{"answer": "TRUE", "reason": "Read the passage."}]},
    {"answers": [{"id": "q1", "reason": "Read the passage."}]},
    {"answers": [{"id": "q1", "answer": "TRUE"}]},
    {"answers": [{"id": 1, "answer": "TRUE", "reason": "Read the passage."}]},
    {"answers": [{"id": "q1", "answer": [], "reason": "Read the passage."}]},
    {"answers": [{"id": "q1", "answer": "TRUE", "reason": ""}]},
    {"answers": [{"id": "q1", "answer": "TRUE", "reason": "A reason", "unexpected": True}]},
    {"answers": [], "unexpected": True},
])
def test_solver_rejects_invalid_json_or_output_schema(content, harness_factory):
    harness = harness_factory(content=content)
    agent = BlindSolverAgent(JsonLLMClient(Settings(), "solver", client=harness.client))
    with pytest.raises(InvalidAgentOutput, match="invalid SolverOutput JSON"):
        agent.run(solver_draft())


@pytest.mark.parametrize("finish", ["length", "content_filter", "tool_calls"])
def test_solver_rejects_incomplete_or_refused_generation(finish, harness_factory):
    draft = solver_draft()
    harness = harness_factory(content=solver_output(draft).model_dump(), finish_reason=finish)
    agent = BlindSolverAgent(JsonLLMClient(Settings(), "solver", client=harness.client))
    with pytest.raises(InvalidAgentOutput):
        agent.run(draft)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_solver_provider_failure_is_sanitized_and_not_retried(status, harness_factory, caplog):
    harness = harness_factory(status=status)
    agent = BlindSolverAgent(JsonLLMClient(Settings(), "solver", client=harness.client))
    with pytest.raises(ProviderError) as raised:
        agent.run(solver_draft())
    assert len(harness.requests) == 1
    for secret in ["RAW_UPSTREAM_SECRET", "offline-test-key"]:
        assert secret not in str(raised.value)
        assert secret not in caplog.text


def test_solver_missing_own_provider_key_fails_before_network():
    settings = Settings(provider="openai", solver_provider="deepseek", deepseek_api_key="")
    agent = BlindSolverAgent(JsonLLMClient(settings, "solver"))
    with pytest.raises(ProviderError, match="Missing DEEPSEEK_API_KEY for solver"):
        agent.run(solver_draft())


def test_complete_independent_solution_agrees_with_all_answer_types():
    draft = solver_draft()
    report = validate_with_solver(draft, solver_output(draft))
    assert report["status"] == "passed"
    assert report["all_items_passed"]
    assert report["protocol_errors"] == []
    assert set(report["items"]) == {question.id for question in draft.questions}
    assert all(item["passed"] for item in report["items"].values())


@pytest.mark.parametrize("protocol", ["missing", "duplicate", "unknown", "empty"])
def test_solver_requires_one_answer_for_every_requested_id(protocol):
    draft = solver_draft()
    output = solver_output(draft)
    if protocol == "missing":
        output.answers.pop()
    elif protocol == "duplicate":
        output.answers.append(output.answers[0].model_copy())
    elif protocol == "unknown":
        output.answers[-1].id = "not-requested"
    else:
        output.answers = []

    report = validate_with_solver(draft, output)

    assert report["status"] == "invalid_protocol"
    assert not report["all_items_passed"]
    assert report["protocol_errors"]
    assert all(not item["passed"] for item in report["items"].values())
    expected = "duplicate_solver_ids" if protocol == "duplicate" else "missing_or_unknown_solver_ids"
    assert expected in report["protocol_errors"]


@pytest.mark.parametrize("answer,expected", [
    ("FALSE", "solver_answer_mismatch"),
    ("true", "invalid_solver_classification"),
    ("YES", "invalid_solver_classification"),
])
def test_solver_tfng_answer_is_compared_and_uses_canonical_labels(answer, expected):
    draft = solver_draft()
    output = solver_output(draft)
    output.answers[0].answer = answer
    report = validate_with_solver(draft, output)
    assert not report["items"]["q1"]["passed"]
    assert expected in report["items"]["q1"]["reasons"]


def test_solver_option_answer_must_be_an_existing_label():
    draft = solver_draft()
    output = solver_output(draft)
    output.answers[1].answer = "Young trees"
    report = validate_with_solver(draft, output)
    assert not report["items"]["q2"]["passed"]
    assert "invalid_solver_option" in report["items"]["q2"]["reasons"]


@pytest.mark.parametrize("kind", ["multiple_choice", "matching_headings"])
def test_case_distinct_valid_option_labels_are_different_answers(kind):
    draft = solver_draft()
    question = draft.questions[0]
    question.kind = kind
    question.options = {"A": "Planting young trees", "a": "River research", "C": "Transport"}
    question.answer = "A"
    if kind == "matching_headings":
        draft.text = "[A]\n" + draft.text
        question.paragraph_id = "A"
    output = solver_output(draft)
    output.answers[0].answer = "a"

    report = validate_with_solver(draft, output)

    assert not report["items"]["q1"]["passed"]
    assert report["items"]["q1"]["reasons"] == ["solver_answer_mismatch"]


@pytest.mark.parametrize("evidence", [None, "", "An invented sentence."])
def test_solver_requires_its_own_verbatim_evidence(evidence):
    draft = solver_draft()
    output = solver_output(draft)
    output.answers[0].evidence_span = evidence
    report = validate_with_solver(draft, output)
    assert not report["items"]["q1"]["passed"]
    assert "solver_evidence_missing_or_not_verbatim" in report["items"]["q1"]["reasons"]


def test_not_given_requires_null_evidence_from_independent_solver():
    draft = solver_draft()
    draft.questions[0].answer = "NOT GIVEN"
    draft.questions[0].evidence_span = None
    output = solver_output(draft)
    assert validate_with_solver(draft, output)["items"]["q1"]["passed"]
    output.answers[0].evidence_span = "Workers plant young trees along the river bank."
    report = validate_with_solver(draft, output)
    assert not report["items"]["q1"]["passed"]
    assert "solver_not_given_has_evidence" in report["items"]["q1"]["reasons"]


@pytest.mark.parametrize("evidence,answer,expected", [
    ("Workers plant young trees along the river bank.", "plant young trees", "solver_completion_word_limit"),
    ("Workers plant young trees along the river bank.", "Young trees", "solver_completion_not_verbatim"),
    ("A well-known reserve protects the coast.", "known", "solver_completion_not_verbatim"),
])
def test_solver_completion_respects_limit_case_and_complete_word(evidence, answer, expected):
    draft = solver_draft()
    draft.text += " " + evidence
    output = solver_output(draft)
    output.answers[2].answer = answer
    output.answers[2].evidence_span = evidence
    report = validate_with_solver(draft, output)
    assert not report["items"]["q3"]["passed"]
    assert expected in report["items"]["q3"]["reasons"]


def test_solver_completion_answer_must_also_be_inside_its_evidence():
    draft = solver_draft()
    draft.text += " The reserve protects coastal forests."
    output = solver_output(draft)
    output.answers[2].evidence_span = "The reserve protects coastal forests."
    report = validate_with_solver(draft, output)
    assert "solver_completion_not_in_evidence" in report["items"]["q3"]["reasons"]


def test_solver_matching_heading_evidence_belongs_to_requested_paragraph():
    draft = solver_draft()
    draft.text = "[A]\n" + draft.text + "\n[B]\nScientists measure the river."
    question = draft.questions[0]
    question.kind = "matching_headings"
    question.options = {"i": "Planting", "ii": "Research", "iii": "Transport"}
    question.paragraph_id = "A"
    question.answer = "i"
    output = solver_output(draft)
    assert validate_with_solver(draft, output)["items"]["q1"]["passed"]
    output.answers[0].evidence_span = "Scientists measure the river."
    report = validate_with_solver(draft, output)
    assert "solver_heading_evidence_outside_target" in report["items"]["q1"]["reasons"]


def test_solver_rejects_blank_explanation_even_if_answers_agree():
    draft = solver_draft()
    output = solver_output(draft)
    output.answers[0].reason = "   "
    report = validate_with_solver(draft, output)
    assert not report["items"]["q1"]["passed"]
    assert "solver_reason_blank" in report["items"]["q1"]["reasons"]
