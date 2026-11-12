"""Verify generated exercises and retry without storage or HTTP dependencies."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from ...core.errors import InvalidAgentOutput, ProviderError
from .models import ExerciseDraft, GenerateRequest
from .listening_rules import apply_listening_rules
from .ports import Generator, Solver
from .rules import validate_rules
from .validation import validate_with_solver


@dataclass
class VerifiedExercise:
    draft: ExerciseDraft
    trace: dict


class VerificationError(RuntimeError):
    def __init__(self, code: str, message: str, trace: dict):
        super().__init__(message)
        self.code = code
        self.trace = trace


class VerifiedGenerationPipeline:
    def __init__(self, generator: Generator, solver: Solver):
        self.generator = generator
        self.solver = solver

    def run(self, request: GenerateRequest) -> VerifiedExercise:
        trace = {
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request": request.model_dump(),
            "metadata": {**self.generator.metadata, **self.solver.metadata},
            "status": "in_progress",
            "attempts": [],
        }
        feedback = []
        for number in range(1, 4):
            attempt = {
                "attempt": number,
                "generator": {"status": "not_run"},
                "rules": {"status": "not_run"},
                "solver": {"status": "not_run"},
                "final_rules": {"status": "not_run"},
            }
            trace["attempts"].append(attempt)
            phase = "generator"
            try:
                draft = self.generator.run(request, deepcopy(feedback))
                attempt["generator"] = {"status": "completed"}
                report = validate_rules(draft, request, enforce_requested_count=True)
                listening_details = apply_listening_rules(draft, request, report)
                attempt["rules"] = asdict(report)
                if listening_details is not None:
                    attempt["listening_rules"] = listening_details
                if report.exercise_errors:
                    attempt["reason"] = "exercise_rule_failure"
                    feedback.append(deepcopy(attempt))
                    continue

                phase = "solver"
                output = self.solver.run(draft)
                solver_report = validate_with_solver(draft, output)
                attempt["solver"] = solver_report
                removed = [
                    question.id for question in draft.questions
                    if report.items[question.id] or not solver_report["items"][question.id]["passed"]
                ]
                attempt["removed_ids"] = removed
                attempt["removed_ratio"] = len(removed) / len(draft.questions)
                if solver_report["protocol_errors"]:
                    attempt["reason"] = "invalid_solver_protocol"
                    feedback.append(deepcopy(attempt))
                    continue

                independent = {answer.id: answer for answer in output.answers}
                retained = draft.model_copy(update={"questions": [
                    question.model_copy(update={
                        "evidence_span": independent[question.id].evidence_span,
                        "explanation": independent[question.id].reason,
                    })
                    for question in draft.questions if question.id not in removed
                ]})
                # Requested count applies before removal. Retained questions
                # must still satisfy all standard exercise/type requirements.
                final_rules = validate_rules(retained, request)
                attempt["final_rules"] = asdict(final_rules)
                if len(removed) * 5 > len(draft.questions) or not final_rules.passed:
                    attempt["reason"] = "too_many_removed_or_invalid_remaining_exercise"
                    feedback.append(deepcopy(attempt))
                    continue

                attempt["published_evidence_source"] = "blind_solver"
                trace["status"] = "verified"
                return VerifiedExercise(draft=retained, trace=trace)
            except InvalidAgentOutput as exc:
                attempt[phase] = {"status": "invalid_output", "error": str(exc)}
                attempt["reason"] = f"invalid_{phase}_output"
                feedback.append(deepcopy(attempt))
            except ProviderError as exc:
                attempt[phase] = {"status": "provider_error", "error": str(exc)}
                attempt["reason"] = f"{phase}_provider_error"
                trace["status"] = "provider_error"
                trace["error"] = str(exc)
                raise VerificationError("provider_error", str(exc), trace) from exc

        trace["status"] = "exhausted"
        raise VerificationError(
            "generation_exhausted",
            "Không thể tạo bài đã kiểm chứng sau 3 lần sinh.",
            trace,
        )
