"""Offline verification/retry tests without safety, API or storage adapters."""

from copy import deepcopy

import pytest

from ielts_agent.agents.uc04.models import ExerciseDraft, GenerateRequest, SolverAnswer, SolverOutput
from ielts_agent.agents.uc04.pipeline import VerificationError, VerifiedGenerationPipeline
from ielts_agent.core.errors import InvalidAgentOutput, ProviderError

from .test_generation import generation_payload


EVIDENCE = "Workers plant young trees along the river bank."


def make_request(skill="reading", count=10):
    return GenerateRequest(
        skill=skill, topic="Coastal habitats", target_band=6,
        question_count=count, completion_word_limit=2,
    )


def make_draft(skill="reading", count=10):
    payload = generation_payload(skill)
    originals = payload["questions"]
    payload["questions"] = [deepcopy(originals[index % len(originals)]) for index in range(count)]
    for index, question in enumerate(payload["questions"], start=1):
        question["id"] = f"q{index}"
    return ExerciseDraft.model_validate(payload)


class FakeGenerator:
    metadata = {
        "provider": "offline", "model": "fixture-generator",
        "prompt_version": "fixture-generation.v1", "skill_hash": "fixture-skill-hash",
    }

    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.calls = 0
        self.feedback = []

    def run(self, request, feedback):
        self.feedback.append(deepcopy(feedback))
        candidate = self.drafts[min(self.calls, len(self.drafts) - 1)]
        self.calls += 1
        if isinstance(candidate, Exception):
            raise candidate
        return candidate.model_copy(deep=True)


class FakeSolver:
    metadata = {
        "solver_provider": "offline", "solver_model": "fixture-solver",
        "solver_prompt_version": "fixture-solver.v1",
    }

    def __init__(self, *, wrong_ids=(), protocol=None, failures=()):
        self.wrong_ids = set(wrong_ids)
        self.protocol = protocol
        self.failures = list(failures)
        self.calls = 0

    def run(self, draft):
        failure = self.failures[min(self.calls, len(self.failures) - 1)] if self.failures else None
        self.calls += 1
        if failure:
            raise failure
        answers = []
        for question in draft.questions:
            answer = {
                "true_false_not_given": "TRUE", "multiple_choice": "A",
                "sentence_completion": "young trees",
            }[question.kind]
            if question.id in self.wrong_ids:
                answer = {"TRUE": "FALSE", "A": "B", "young trees": "trees"}[answer]
            answers.append(SolverAnswer(
                id=question.id, answer=answer, evidence_span=EVIDENCE,
                reason="Independently identified the planting sentence.",
            ))
        if self.protocol == "missing":
            answers.pop()
        elif self.protocol == "duplicate":
            answers.append(answers[0].model_copy())
        elif self.protocol == "unknown":
            answers[-1] = answers[-1].model_copy(update={"id": "unknown-question"})
        return SolverOutput(answers=answers)


@pytest.mark.parametrize("skill", ["reading", "listening"])
def test_verified_pipeline_returns_both_skills_and_a_complete_attempt_trace(skill):
    request = make_request(skill)
    generator = FakeGenerator([make_draft(skill)])
    solver = FakeSolver()

    result = VerifiedGenerationPipeline(generator, solver).run(request)

    assert len(result.draft.questions) == 10
    assert len({question.kind for question in result.draft.questions}) == 3
    assert generator.calls == solver.calls == 1
    assert result.trace["id"] and result.trace["created_at"]
    assert result.trace["request"] == request.model_dump()
    assert result.trace["metadata"] == {**generator.metadata, **solver.metadata}
    assert result.trace["status"] == "verified"
    assert len(result.trace["attempts"]) == 1
    attempt = result.trace["attempts"][0]
    assert attempt["attempt"] == 1
    assert not attempt["rules"]["exercise_errors"]
    assert attempt["solver"]["all_items_passed"]
    assert attempt["removed_ids"] == []
    assert attempt["removed_ratio"] == 0
    assert not attempt["final_rules"]["exercise_errors"]
    assert attempt["published_evidence_source"] == "blind_solver"


def test_removing_exactly_twenty_percent_is_accepted_when_remaining_shape_is_valid():
    generator = FakeGenerator([make_draft()])
    solver = FakeSolver(wrong_ids={"q1", "q2"})

    result = VerifiedGenerationPipeline(generator, solver).run(make_request())

    assert len(result.draft.questions) == 8
    assert len({question.kind for question in result.draft.questions}) == 3
    assert {question.id for question in result.draft.questions}.isdisjoint({"q1", "q2"})
    assert generator.calls == solver.calls == 1
    attempt = result.trace["attempts"][0]
    assert set(attempt["removed_ids"]) == {"q1", "q2"}
    assert attempt["removed_ratio"] == pytest.approx(0.2)


def test_more_than_twenty_percent_is_rejected_even_if_ten_valid_questions_remain():
    generator = FakeGenerator([make_draft(count=13)])
    solver = FakeSolver(wrong_ids={"q1", "q2", "q3"})

    with pytest.raises(VerificationError) as raised:
        VerifiedGenerationPipeline(generator, solver).run(make_request(count=13))

    assert raised.value.code == "generation_exhausted"
    assert raised.value.trace["status"] == "exhausted"
    assert generator.calls == solver.calls == 3
    assert len(raised.value.trace["attempts"]) == 3
    for attempt in raised.value.trace["attempts"]:
        assert attempt["removed_ratio"] > 0.2
        assert len(attempt["removed_ids"]) == 3
        assert not attempt["final_rules"]["exercise_errors"]


def test_removal_below_twenty_percent_still_regenerates_when_fewer_than_eight_remain():
    generator = FakeGenerator([make_draft(count=8)])
    solver = FakeSolver(wrong_ids={"q1"})

    with pytest.raises(VerificationError) as raised:
        VerifiedGenerationPipeline(generator, solver).run(make_request(count=8))

    assert generator.calls == 3
    for attempt in raised.value.trace["attempts"]:
        assert attempt["removed_ratio"] < 0.2
        assert any(error.startswith("question_count:7;") for error in attempt["final_rules"]["exercise_errors"])


def test_removal_losing_a_question_type_regenerates_even_with_nine_questions():
    candidate = make_draft()
    for question in candidate.questions[1:]:
        if question.kind == "true_false_not_given":
            question.kind = "multiple_choice"
            question.options = {"A": "Young trees", "B": "Flowers", "C": "Rice"}
            question.answer = "A"
    generator = FakeGenerator([candidate])
    solver = FakeSolver(wrong_ids={"q1"})

    with pytest.raises(VerificationError) as raised:
        VerifiedGenerationPipeline(generator, solver).run(make_request())

    assert generator.calls == 3
    for attempt in raised.value.trace["attempts"]:
        assert attempt["removed_ratio"] == pytest.approx(0.1)
        assert "at_least_three_question_types_required" in attempt["final_rules"]["exercise_errors"]


def test_invalid_first_candidate_regenerates_with_feedback_without_calling_solver():
    invalid = make_draft()
    invalid.text = "A passage that is much too short."
    generator = FakeGenerator([invalid, make_draft()])
    solver = FakeSolver()

    result = VerifiedGenerationPipeline(generator, solver).run(make_request())

    assert generator.calls == 2 and solver.calls == 1
    assert generator.feedback[0] == []
    assert generator.feedback[1]
    attempts = result.trace["attempts"]
    assert [attempt["attempt"] for attempt in attempts] == [1, 2]
    assert attempts[0]["rules"]["exercise_errors"]
    assert attempts[0]["reason"]
    assert result.trace["status"] == "verified"


@pytest.mark.parametrize("protocol", ["missing", "duplicate", "unknown"])
def test_incomplete_ambiguous_or_unknown_solver_ids_cannot_be_accepted(protocol):
    generator = FakeGenerator([make_draft()])
    solver = FakeSolver(protocol=protocol)

    with pytest.raises(VerificationError) as raised:
        VerifiedGenerationPipeline(generator, solver).run(make_request())

    assert raised.value.code == "generation_exhausted"
    assert generator.calls == solver.calls == 3
    assert all(attempt["solver"]["protocol_errors"] for attempt in raised.value.trace["attempts"])


def test_malformed_solver_responses_fail_closed_and_exhaust_three_candidates():
    generator = FakeGenerator([make_draft()])
    solver = FakeSolver(failures=[InvalidAgentOutput("solver returned invalid JSON")])

    with pytest.raises(VerificationError) as raised:
        VerifiedGenerationPipeline(generator, solver).run(make_request())

    assert raised.value.code == "generation_exhausted"
    assert generator.calls == solver.calls == 3
    assert len(raised.value.trace["attempts"]) == 3
    assert all(attempt["reason"] for attempt in raised.value.trace["attempts"])
    assert all(attempt["solver"]["status"] == "invalid_output"
               for attempt in raised.value.trace["attempts"])
    assert all(attempt["solver"]["error"] == "solver returned invalid JSON"
               for attempt in raised.value.trace["attempts"])


def test_transient_malformed_solver_output_regenerates_and_preserves_failed_attempt():
    generator = FakeGenerator([make_draft()])
    solver = FakeSolver(failures=[InvalidAgentOutput("solver returned invalid JSON"), None])

    result = VerifiedGenerationPipeline(generator, solver).run(make_request())

    assert generator.calls == solver.calls == 2
    assert result.trace["status"] == "verified"
    assert len(result.trace["attempts"]) == 2
    failed, accepted = result.trace["attempts"]
    assert failed["solver"] == {"status": "invalid_output", "error": "solver returned invalid JSON"}
    assert failed["reason"] == "invalid_solver_output"
    assert generator.feedback[1][0]["reason"] == "invalid_solver_output"
    assert accepted["solver"]["all_items_passed"]
    assert accepted["published_evidence_source"] == "blind_solver"


@pytest.mark.parametrize("stage", ["generator", "solver"])
def test_provider_errors_stop_without_accepting_a_candidate(stage):
    generator = FakeGenerator([ProviderError("generator unavailable")] if stage == "generator" else [make_draft()])
    solver = FakeSolver(failures=[ProviderError("solver unavailable")] if stage == "solver" else [])

    with pytest.raises(VerificationError) as raised:
        VerifiedGenerationPipeline(generator, solver).run(make_request())

    assert raised.value.code == "provider_error"
    assert raised.value.trace["status"] == "provider_error"
    assert generator.calls == 1
    assert solver.calls == (1 if stage == "solver" else 0)
    assert len(raised.value.trace["attempts"]) == 1
    attempt = raised.value.trace["attempts"][0]
    assert attempt[stage]["status"] == "provider_error"
    assert attempt[stage]["error"] == f"{stage} unavailable"
    assert attempt["reason"] == f"{stage}_provider_error"
    assert "unavailable" in str(raised.value)


def test_invalid_generator_output_stops_with_a_clear_error_after_three_attempts():
    generator = FakeGenerator([InvalidAgentOutput("generator returned invalid JSON")])
    solver = FakeSolver()

    with pytest.raises(VerificationError) as raised:
        VerifiedGenerationPipeline(generator, solver).run(make_request())

    assert raised.value.code == "generation_exhausted"
    assert str(raised.value)
    assert generator.calls == 3 and solver.calls == 0
    assert raised.value.trace["status"] == "exhausted"
    assert [attempt["attempt"] for attempt in raised.value.trace["attempts"]] == [1, 2, 3]
    assert all(attempt["reason"] for attempt in raised.value.trace["attempts"])


def test_retained_evidence_and_explanation_are_selected_by_solver_without_mutating_candidate():
    candidate = make_draft()
    candidate.text += " The reserve is open to local schools."
    candidate.questions[0].evidence_span = "The reserve is open to local schools."
    candidate.questions[0].explanation = "GENERATOR_EXPLANATION"
    original = candidate.model_dump()

    result = VerifiedGenerationPipeline(FakeGenerator([candidate]), FakeSolver()).run(make_request())

    retained = result.draft.questions[0]
    assert retained.answer == "TRUE"
    assert retained.evidence_span == EVIDENCE
    assert retained.explanation == "Independently identified the planting sentence."
    assert candidate.model_dump() == original


def test_option_labels_that_differ_by_case_are_not_treated_as_the_same_answer():
    candidate = make_draft()
    candidate.questions[1].options = {
        "A": "Young trees", "a": "Rice fields", "B": "Flowers", "C": "Rice",
    }
    candidate.questions[1].answer = "a"

    result = VerifiedGenerationPipeline(FakeGenerator([candidate]), FakeSolver()).run(make_request())

    assert len(result.draft.questions) == 9
    assert "q2" not in {question.id for question in result.draft.questions}
    attempt = result.trace["attempts"][0]
    assert attempt["rules"]["items"]["q2"] == []
    assert attempt["removed_ids"] == ["q2"]
    assert "solver_answer_mismatch" in attempt["solver"]["items"]["q2"]["reasons"]
