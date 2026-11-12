"""Fail-closed generation pipeline: rules -> blind solver -> atomic bank write."""

from dataclasses import asdict
from datetime import datetime, timezone
import json
from uuid import uuid4

from .models import GenerateRequest
from ...core.errors import DuplicateError, InvalidAgentOutput, ProviderError
from .listening_rules import apply_listening_rules
from .rules import validate_rules
from .validation import validate_with_solver
from .ports import ExerciseBank, PracticeAgents


class GenerationError(RuntimeError):
    def __init__(self, code: str, message: str, trace_id: str, status_code: int = 422):
        super().__init__(message)
        self.code, self.trace_id, self.status_code = code, trace_id, status_code


class UC04Agent:
    def __init__(self, bank: ExerciseBank, agents: PracticeAgents):
        self.bank, self.agents = bank, agents

    def run(self, request: GenerateRequest) -> dict:
        trace = {
            "id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
            "request": request.model_dump(), "metadata": self.agents.metadata,
            "status": "in_progress", "attempts": [],
        }
        try:
            decision = self.agents.safety.run(request.topic)
            trace["topic_safety"] = decision.model_dump()
            if not decision.allowed:
                trace["status"] = "unsafe_topic"
                raise GenerationError("unsafe_topic", "Chủ đề không phù hợp; hãy chọn một chủ đề học thuật khác.", trace["id"], 400)
            feedback = []
            # Initial candidate plus at most two full regenerations.
            for number in range(1, 4):
                attempt = {"attempt": number, "rules": {"status": "not_run"}, "solver": {"status": "not_run"}}
                trace["attempts"].append(attempt)
                try:
                    draft = self.agents.generator.run(request, feedback)
                    report = validate_rules(draft, request, enforce_requested_count=True)
                    listening_details = apply_listening_rules(draft, request, report)
                    attempt["rules"] = asdict(report)
                    if listening_details is not None:
                        attempt["listening_rules"] = listening_details
                    if report.exercise_errors:
                        attempt["reason"] = "exercise_rule_failure"
                        feedback.append(attempt.copy())
                        self.bank.save_trace(trace)
                        continue
                    content = draft.model_dump()
                    generated_safety = self.agents.safety.run(json.dumps(content, ensure_ascii=False))
                    attempt["content_safety"] = generated_safety.model_dump()
                    if not generated_safety.allowed:
                        attempt["reason"] = "unsafe_generated_content"
                        feedback.append({"attempt": number, "reason": "unsafe_generated_content; use a safe educational treatment"})
                        self.bank.save_trace(trace)
                        continue
                    output = self.agents.solver.run(draft)
                    solver = validate_with_solver(draft, output)
                    attempt["solver"] = solver
                    removed = [q.id for q in draft.questions if report.items[q.id] or not solver["items"][q.id]["passed"]]
                    attempt["removed_ids"] = removed
                    attempt["removed_ratio"] = len(removed) / len(draft.questions)
                    independent_answers = {answer.id: answer for answer in output.answers}
                    # Publish the independently selected support, rather than an
                    # unrelated generator quote that merely exists in the text.
                    retained = draft.model_copy(update={"questions": [
                        q.model_copy(update={"evidence_span": independent_answers[q.id].evidence_span,
                                             "explanation": independent_answers[q.id].reason})
                        for q in draft.questions if q.id not in removed
                    ]})
                    final_rules = validate_rules(retained, request)
                    attempt["final_rules"] = asdict(final_rules)
                    if len(removed) * 5 > len(draft.questions) or not final_rules.passed or solver["protocol_errors"]:
                        attempt["reason"] = "too_many_removed_or_invalid_remaining_exercise"
                        feedback.append(attempt.copy())
                        self.bank.save_trace(trace)
                        continue
                    attempt["published_evidence_source"] = "blind_solver"
                    final_safety = self.agents.safety.run(retained.model_dump_json())
                    attempt["final_content_safety"] = final_safety.model_dump()
                    if not final_safety.allowed:
                        attempt["reason"] = "unsafe_solver_content"
                        feedback.append({"attempt": number, "reason": "unsafe_solver_content"})
                        self.bank.save_trace(trace)
                        continue
                    try:
                        return self.bank.save_verified(request, retained, self.agents.metadata, trace)
                    except DuplicateError as exc:
                        attempt["dedup"] = {"passed": False, "similarity": exc.similarity, "matched_item_id": exc.item_id}
                        feedback.append({"attempt": number, "reason": "passage_too_similar_to_bank; create a substantially different original passage"})
                        self.bank.save_trace(trace)
                except InvalidAgentOutput as exc:
                    attempt["reason"] = str(exc)
                    feedback.append({"attempt": number, "reason": str(exc)})
                    self.bank.save_trace(trace)
            trace["status"] = "exhausted"
            raise GenerationError("generation_exhausted", "Không thể tạo bài đã kiểm chứng sau 3 lần sinh.", trace["id"])
        except (ProviderError, InvalidAgentOutput) as exc:
            trace["status"] = "provider_error"
            trace["error"] = str(exc)
            raise GenerationError("provider_error", str(exc), trace["id"], 503) from exc
        finally:
            # Bank atomically saves successful traces with content. Failure traces
            # are saved here even when an upstream request fails before solving.
            if trace["status"] != "verified":
                self.bank.save_trace(trace)
