"""UC-04 interfaces implemented by infrastructure and deterministic test doubles."""

from typing import Protocol
from .models import ExerciseDraft, GenerateRequest, SafetyDecision, SolverOutput


class Generator(Protocol):
    metadata: dict

    def run(self, request: GenerateRequest, feedback: list[dict]) -> ExerciseDraft: ...


class Solver(Protocol):
    metadata: dict

    def run(self, draft: ExerciseDraft) -> SolverOutput: ...


class Safety(Protocol):
    def run(self, text: str) -> SafetyDecision: ...


class PracticeAgents(Protocol):
    metadata: dict
    generator: Generator
    solver: Solver
    safety: Safety


class ExerciseBank(Protocol):
    def save_trace(self, trace: dict) -> None: ...
    def save_verified(self, request: GenerateRequest, draft: ExerciseDraft, metadata: dict, trace: dict) -> dict: ...
