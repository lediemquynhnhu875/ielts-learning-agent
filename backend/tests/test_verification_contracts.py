"""Solver/safety contracts kept separate from deterministic rule validation."""

import pytest
from pydantic import ValidationError

from ielts_agent.agents.uc04.models import (
    GenerateRequest, SafetyDecision, SolverAnswer, SolverOutput,
)
from ielts_agent.agents.uc04.validation import validate_with_solver

from .test_rules import draft, request


def test_public_projection_excludes_answer_fields():
    public = draft().questions[0].public().model_dump()
    assert set(public) == {"id", "kind", "prompt", "options", "word_limit", "paragraph_id"}
    assert "answer" not in public and "evidence_span" not in public


def test_solver_heading_quote_must_belong_to_target_paragraph():
    exercise = draft()
    exercise.text = "[A]\n" + exercise.text + "\n[B]\nScientists monitor local rivers."
    question = exercise.questions[0]
    question.kind = "matching_headings"
    question.options = {"i": "Forest protection", "ii": "Scientific research", "iii": "Industry"}
    question.paragraph_id = "A"
    question.answer = "i"
    output = SolverOutput(answers=[SolverAnswer(id=q.id, answer=q.answer,
        evidence_span="Scientists monitor local rivers." if q.id == "1" else q.evidence_span,
        reason="Independent interpretation") for q in exercise.questions])
    report = validate_with_solver(exercise, output)
    assert "solver_heading_evidence_outside_target" in report["items"]["1"]["reasons"]


def test_request_half_band_and_safety_bool_are_strict():
    assert request().target_band == 6
    with pytest.raises(ValidationError):
        GenerateRequest(skill="reading", topic="Metro", target_band=6.3)
    with pytest.raises(ValidationError):
        SafetyDecision(allowed="false", reason="inappropriate")
    with pytest.raises(ValidationError):
        GenerateRequest(skill="reading", topic=" x ", target_band=6)
