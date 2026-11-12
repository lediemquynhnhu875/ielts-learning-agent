"""Offline orchestration tests; synthetic fixtures are not a human benchmark."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from ielts_agent.agents.uc04.models import (
    ExerciseDraft, GenerateRequest, SafetyDecision, SolverAnswer, SolverOutput,
)
from ielts_agent.agents.uc04.rules import word_count
from ielts_agent.core.errors import InvalidAgentOutput, ProviderError
from ielts_agent.agents.uc04.agent import GenerationError, UC04Agent
from ielts_agent.agents.uc04.validation import validate_with_solver


def practice_request(skill="reading", count=10):
    return GenerateRequest(
        skill=skill,
        topic="Can Gio mangrove restoration",
        target_band=6.0,
        question_count=count,
        completion_word_limit=2,
    )


def practice_draft(skill="reading", count=10):
    text = (
        "The reserve protects coastal forests. Workers plant young trees. "
        "The research team measures water quality every month. "
    )
    target = 650 if skill == "reading" else 500
    # Deliberate fixture padding keeps structural checks deterministic. It is
    # never represented as an actual generated or human-reviewed exercise.
    text += " ".join(["habitat"] * (target - word_count(text)))
    kinds = ["true_false_not_given", "multiple_choice", "sentence_completion"]
    questions = []
    for index in range(count):
        kind = kinds[index % 3]
        questions.append({
            "id": f"q{index + 1}",
            "kind": kind,
            "prompt": (
                "Workers plant ____ near the reserve. Write NO MORE THAN TWO WORDS."
                if kind == "sentence_completion"
                else "The reserve protects coastal forests."
            ),
            "options": {"A": "Coastal forests", "B": "Factories", "C": "Railways"}
            if kind == "multiple_choice" else {},
            "word_limit": 2 if kind == "sentence_completion" else None,
            "paragraph_id": None,
            "answer": {"true_false_not_given": "TRUE", "multiple_choice": "A", "sentence_completion": "young trees"}[kind],
            "evidence_span": "Workers plant young trees." if kind == "sentence_completion" else "The reserve protects coastal forests.",
            "explanation": "The quoted sentence states the relevant fact.",
        })
    if skill == "listening":
        # Listening answers must come up in script order (listening_rules.py).
        questions.sort(key=lambda question: question["kind"] == "sentence_completion")
    return ExerciseDraft(title="Restoring a coastal habitat", text=text, questions=questions)


class FakeAgents:
    metadata = {
        "model": "fake-generator",
        "prompt_version": "test.generator.v1",
        "solver_model": "fake-solver",
        "solver_prompt_version": "test.solver.v1",
        "skill_hash": "offline-test-skill",
    }

    def __init__(self, drafts, *, wrong_ids=(), safety_results=None, solver_protocol=None):
        self.drafts = list(drafts)
        self.wrong_ids = set(wrong_ids)
        self.safety_results = list(safety_results or [])
        self.solver_protocol = solver_protocol
        self.generate_calls = 0
        self.solve_calls = 0
        self.safety_calls = []
        self.feedback = []
        self.generator = SimpleNamespace(run=self.generate)
        self.solver = SimpleNamespace(run=self.solve)
        self.safety = SimpleNamespace(run=self.check_safety)

    def check_safety(self, text):
        self.safety_calls.append(text)
        if self.safety_results:
            allowed = self.safety_results.pop(0)
        else:
            allowed = True
        return SafetyDecision(allowed=allowed, reason="Offline policy decision")

    def generate(self, request, feedback):
        self.generate_calls += 1
        self.feedback.append(deepcopy(feedback))
        candidate = self.drafts[min(self.generate_calls - 1, len(self.drafts) - 1)]
        if isinstance(candidate, Exception):
            raise candidate
        return candidate.model_copy(deep=True)

    def solve(self, draft):
        self.solve_calls += 1
        answers = []
        # The fake solves the fixture's simple known facts independently of
        # generated keys; intentionally corrupting a key does not change it.
        for question in draft.questions:
            answer = {
                "true_false_not_given": "TRUE",
                "multiple_choice": "A",
                "sentence_completion": "young trees",
            }[question.kind]
            evidence = "Workers plant young trees." if question.kind == "sentence_completion" else "The reserve protects coastal forests."
            if question.id in self.wrong_ids:
                answer = "FALSE" if question.kind == "true_false_not_given" else "unrelated"
            answers.append(SolverAnswer(id=question.id, answer=answer, evidence_span=evidence, reason="Independently read the fixture sentence."))
        if self.solver_protocol == "missing":
            answers.pop()
        elif self.solver_protocol == "duplicate":
            answers.append(answers[0].model_copy())
        elif self.solver_protocol == "unknown":
            answers.append(answers[0].model_copy(update={"id": "unknown"}))
        return SolverOutput(answers=answers)


class RecordingBank:
    def __init__(self):
        self.saved = []
        self.traces = {}

    def save_trace(self, trace):
        self.traces[trace["id"]] = deepcopy(trace)

    def get_trace(self, trace_id):
        return self.traces.get(trace_id)

    def save_verified(self, request, draft, metadata, trace):
        self.saved.append(draft.model_copy(deep=True))
        trace.update(status="verified", item_id="saved")
        self.save_trace(trace)
        return {"id": "saved", "question_count": len(draft.questions), "trace_id": trace["id"]}


def run_with(agents, request=None):
    bank = RecordingBank()
    service = UC04Agent(bank, agents)
    result = service.run(request or practice_request())
    return bank, result


@pytest.mark.parametrize("skill", ["reading", "listening"])
def test_reading_6_and_listening_two_word_completion_pass_both_layers(skill):
    agents = FakeAgents([practice_draft(skill)])
    bank, result = run_with(agents, practice_request(skill))
    assert result["question_count"] == 10
    assert len({q.kind for q in bank.saved[0].questions}) == 3
    completions = [q for q in bank.saved[0].questions if q.kind == "sentence_completion"]
    assert all(q.word_limit == 2 and word_count(q.answer) <= 2 for q in completions)
    trace = bank.get_trace(result["trace_id"])
    assert trace["status"] == "verified"
    attempt = trace["attempts"][0]
    assert not attempt["rules"]["exercise_errors"]
    assert not any(attempt["rules"]["items"].values())
    assert all(item["passed"] for item in attempt["solver"]["items"].values())
    assert agents.generate_calls == agents.solve_calls == 1


@pytest.mark.parametrize("bad_answer", ["FALSE", "NOT GIVEN"])
def test_injected_wrong_tfng_key_is_removed_by_blind_solver(bad_answer):
    exercise = practice_draft()
    exercise.questions[0].answer = bad_answer
    if bad_answer == "NOT GIVEN":
        exercise.questions[0].evidence_span = None
    bank, result = run_with(FakeAgents([exercise]))
    assert result["question_count"] == 9
    assert "q1" not in {q.id for q in bank.saved[0].questions}
    report = bank.get_trace(result["trace_id"])["attempts"][0]
    assert report["rules"]["items"]["q1"] == []
    assert "solver_answer_mismatch" in report["solver"]["items"]["q1"]["reasons"]


def test_over_limit_completion_is_removed_even_when_answer_occurs_verbatim():
    exercise = practice_draft()
    exercise.questions[2].answer = "plant young trees"
    bank, result = run_with(FakeAgents([exercise]))
    assert result["question_count"] == 9
    attempt = bank.get_trace(result["trace_id"])["attempts"][0]
    assert "completion_answer_exceeds_word_limit" in attempt["rules"]["items"]["q3"]
    assert "q3" not in {q.id for q in bank.saved[0].questions}


def test_exact_twenty_percent_removal_keeps_valid_eight_question_exercise():
    agents = FakeAgents([practice_draft()], wrong_ids={"q1", "q4"})
    bank, result = run_with(agents)
    assert result["question_count"] == 8
    assert len(bank.saved) == 1 and agents.generate_calls == 1
    attempt = bank.get_trace(result["trace_id"])["attempts"][0]
    assert attempt["removed_ratio"] == 0.2
    assert len({q.kind for q in bank.saved[0].questions}) == 3


def test_more_than_twenty_percent_forces_regeneration_and_stops_after_three_candidates():
    agents = FakeAgents([practice_draft(count=13)], wrong_ids={"q1", "q4", "q7"})
    bank = RecordingBank()
    with pytest.raises(GenerationError) as raised:
        UC04Agent(bank, agents).run(practice_request(count=13))
    assert raised.value.code == "generation_exhausted"
    assert agents.generate_calls == agents.solve_calls == 3
    assert not bank.saved
    trace = bank.get_trace(raised.value.trace_id)
    assert trace["status"] == "exhausted"
    assert all(attempt["removed_ratio"] > 0.2 for attempt in trace["attempts"])
    assert all(len(attempt["removed_ids"]) == 3 for attempt in trace["attempts"])


def test_removal_leaving_fewer_than_eight_regenerates():
    exercise = practice_draft(count=8)
    agents = FakeAgents([exercise], wrong_ids={"q1"})
    bank = RecordingBank()
    with pytest.raises(GenerationError):
        UC04Agent(bank, agents).run(practice_request(count=8))
    assert agents.generate_calls == 3
    assert not bank.saved


def test_removal_losing_third_question_type_regenerates():
    exercise = practice_draft()
    for question in exercise.questions[1:]:
        if question.kind == "true_false_not_given":
            question.kind = "multiple_choice"
            question.options = {"A": "Coastal forests", "B": "Factories", "C": "Railways"}
            question.answer = "A"
    agents = FakeAgents([exercise], wrong_ids={"q1"})
    bank = RecordingBank()
    with pytest.raises(GenerationError):
        UC04Agent(bank, agents).run(practice_request())
    assert agents.generate_calls == 3
    assert not bank.saved
    final = next(iter(bank.traces.values()))["attempts"][-1]
    assert "at_least_three_question_types_required" in final["final_rules"]["exercise_errors"]


@pytest.mark.parametrize("protocol", ["missing", "duplicate", "unknown"])
def test_incomplete_or_ambiguous_solver_protocol_never_publishes(protocol):
    agents = FakeAgents([practice_draft()], solver_protocol=protocol)
    bank = RecordingBank()
    with pytest.raises(GenerationError) as raised:
        UC04Agent(bank, agents).run(practice_request())
    assert agents.generate_calls == 3 and not bank.saved
    attempts = bank.get_trace(raised.value.trace_id)["attempts"]
    assert all(attempt["solver"]["protocol_errors"] for attempt in attempts)


def test_invalid_first_passage_is_regenerated_with_feedback():
    invalid = practice_draft()
    invalid.text = "This passage is far too short."
    agents = FakeAgents([invalid, practice_draft()])
    bank, result = run_with(agents)
    assert agents.generate_calls == 2 and agents.solve_calls == 1
    assert agents.feedback[1]
    assert len(bank.get_trace(result["trace_id"])["attempts"]) == 2


def test_unsuitable_requested_topic_is_refused_before_generation():
    agents = FakeAgents([practice_draft()], safety_results=[False])
    bank = RecordingBank()
    with pytest.raises(GenerationError) as raised:
        UC04Agent(bank, agents).run(practice_request())
    assert raised.value.code == "unsafe_topic"
    assert agents.generate_calls == agents.solve_calls == 0
    assert not bank.saved
    assert bank.get_trace(raised.value.trace_id)["topic_safety"]["allowed"] is False


def test_unsafe_generated_content_never_reaches_solver_or_bank():
    agents = FakeAgents([practice_draft()], safety_results=[True, False, False, False])
    bank = RecordingBank()
    with pytest.raises(GenerationError) as raised:
        UC04Agent(bank, agents).run(practice_request())
    assert agents.generate_calls == 3 and agents.solve_calls == 0
    assert not bank.saved
    trace = bank.get_trace(raised.value.trace_id)
    assert all(attempt["reason"] == "unsafe_generated_content" for attempt in trace["attempts"])


def test_provider_failure_is_recorded_and_never_publishes():
    agents = FakeAgents([ProviderError("generator provider request failed")])
    bank = RecordingBank()
    with pytest.raises(GenerationError) as raised:
        UC04Agent(bank, agents).run(practice_request())
    assert raised.value.code == "provider_error"
    assert raised.value.status_code == 503
    assert not bank.saved
    assert bank.get_trace(raised.value.trace_id)["status"] == "provider_error"


def test_malformed_generator_json_exhausts_only_three_candidates():
    agents = FakeAgents([InvalidAgentOutput("generator returned invalid JSON")])
    bank = RecordingBank()
    with pytest.raises(GenerationError) as raised:
        UC04Agent(bank, agents).run(practice_request())
    assert raised.value.code == "generation_exhausted"
    assert agents.generate_calls == 3 and not bank.saved


def test_solver_requires_own_verbatim_evidence():
    exercise = practice_draft()
    output = FakeAgents([exercise]).solve(exercise)
    output.answers[0].evidence_span = "An invented supporting sentence."
    report = validate_with_solver(exercise, output)
    assert not report["items"]["q1"]["passed"]
    assert "solver_evidence_missing_or_not_verbatim" in report["items"]["q1"]["reasons"]


def test_published_evidence_and_explanation_come_from_independent_solver():
    exercise = practice_draft()
    # The generator's quote exists but is unrelated to the TRUE statement.
    exercise.questions[0].evidence_span = "Workers plant young trees."
    bank, result = run_with(FakeAgents([exercise]))
    published = bank.saved[0].questions[0]
    assert published.evidence_span == "The reserve protects coastal forests."
    assert published.explanation == "Independently read the fixture sentence."
    attempt = bank.get_trace(result["trace_id"])["attempts"][0]
    assert attempt["published_evidence_source"] == "blind_solver"
    assert not attempt["final_rules"]["items"]["q1"]


def test_solver_explanations_are_safety_checked_before_publication():
    agents = FakeAgents([practice_draft()], safety_results=[True, True, False, True, False, True, False])
    bank = RecordingBank()
    with pytest.raises(GenerationError):
        UC04Agent(bank, agents).run(practice_request())
    assert not bank.saved
    assert agents.generate_calls == 3
    attempts = next(iter(bank.traces.values()))["attempts"]
    assert all(attempt["reason"] == "unsafe_solver_content" for attempt in attempts)


def test_duplicate_bank_candidate_is_regenerated_and_traced():
    from ielts_agent.core.errors import DuplicateError

    class OnceDuplicateBank(RecordingBank):
        attempts = 0

        def save_verified(self, request, draft, metadata, trace):
            self.attempts += 1
            if self.attempts == 1:
                raise DuplicateError(0.95, "existing-content")
            return super().save_verified(request, draft, metadata, trace)

    bank = OnceDuplicateBank()
    agents = FakeAgents([practice_draft()])
    result = UC04Agent(bank, agents).run(practice_request())
    attempts = bank.get_trace(result["trace_id"])["attempts"]
    assert len(attempts) == 2 and agents.generate_calls == 2
    assert attempts[0]["dedup"]["passed"] is False
    assert len(bank.saved) == 1
