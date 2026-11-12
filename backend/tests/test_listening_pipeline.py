"""Listening rules are applied by both generation paths and Reading is untouched."""

from types import SimpleNamespace

import pytest

from ielts_agent.agents.uc04.agent import UC04Agent
from ielts_agent.agents.uc04.models import SolverAnswer, SolverOutput
from ielts_agent.agents.uc04.pipeline import VerifiedGenerationPipeline

from .test_pipeline import FakeAgents, RecordingBank, practice_draft, practice_request

SURNAME_ID = "q10"


class EchoSolver:
    """Blind-solver stand-in that always agrees with the key, so only rules can remove a question."""

    metadata = {"solver_model": "echo"}

    def run(self, draft):
        return SolverOutput(answers=[
            SolverAnswer(
                id=q.id, answer=q.answer, evidence_span=q.evidence_span,
                reason="Read the script directly.",
            )
            for q in draft.questions
        ])


class FixedGenerator:
    metadata = {"model": "fixed"}

    def __init__(self, draft):
        self.draft = draft

    def run(self, request, feedback):
        return self.draft.model_copy(deep=True)


def listening_draft(skill="listening", spelled=False):
    """Ten questions in script order; the last one asks for a surname."""
    draft = practice_draft(skill)
    sentence = " Caller: It's Hart, H-A-R-T." if spelled else " Caller: It's Hart."
    evidence = sentence.split("Caller: ")[1]
    ordered = sorted(draft.questions, key=lambda q: q.kind == "sentence_completion")
    last = ordered[-1].model_copy(update={
        "id": SURNAME_ID,
        "prompt": "Surname of the caller: ____",
        "answer": "Hart",
        "evidence_span": evidence,
    })
    others = [q for q in ordered if q.id != SURNAME_ID][:9]
    return draft.model_copy(update={"text": draft.text + sentence, "questions": others + [last]})


def run_agent(draft, skill="listening"):
    agents = FakeAgents([draft])
    agents.solver = SimpleNamespace(run=EchoSolver().run)
    bank = RecordingBank()
    result = UC04Agent(bank, agents).run(practice_request(skill))
    return bank, result


def test_agent_removes_unspelled_name_and_traces_listening_rules():
    bank, result = run_agent(listening_draft())
    trace = bank.get_trace(result["trace_id"])
    attempt = trace["attempts"][0]
    assert attempt["rules"]["items"][SURNAME_ID] == ["listening_name_not_spelled"]
    assert attempt["removed_ids"] == [SURNAME_ID]
    assert attempt["listening_rules"]["name_checks"][SURNAME_ID] == "confirmed"
    assert result["question_count"] == 9


def test_agent_keeps_a_correctly_spelled_name():
    bank, result = run_agent(listening_draft(spelled=True))
    attempt = bank.get_trace(result["trace_id"])["attempts"][0]
    assert attempt["removed_ids"] == []
    assert result["question_count"] == 10


def test_agent_does_not_apply_listening_rules_to_reading():
    bank, result = run_agent(listening_draft(skill="reading"), skill="reading")
    attempt = bank.get_trace(result["trace_id"])["attempts"][0]
    assert "listening_rules" not in attempt
    assert attempt["removed_ids"] == []


def run_pipeline(draft, skill="listening"):
    pipeline = VerifiedGenerationPipeline(FixedGenerator(draft), EchoSolver())
    return pipeline.run(practice_request(skill))


def test_pipeline_removes_unspelled_name_and_traces_listening_rules():
    result = run_pipeline(listening_draft())
    attempt = result.trace["attempts"][0]
    assert attempt["rules"]["items"][SURNAME_ID] == ["listening_name_not_spelled"]
    assert attempt["removed_ids"] == [SURNAME_ID]
    assert attempt["listening_rules"]["name_checks"][SURNAME_ID] == "confirmed"
    assert len(result.draft.questions) == 9


def test_pipeline_keeps_a_correctly_spelled_name():
    result = run_pipeline(listening_draft(spelled=True))
    assert result.trace["attempts"][0]["removed_ids"] == []
    assert len(result.draft.questions) == 10


def test_pipeline_does_not_apply_listening_rules_to_reading():
    result = run_pipeline(listening_draft(skill="reading"), skill="reading")
    assert "listening_rules" not in result.trace["attempts"][0]
