"""Independent solver comparison and evidence verification tools."""

from .models import ExerciseDraft, SolverOutput
from .rules import _paragraphs, contains_phrase, word_count


def _canonical(answer: str) -> str:
    return " ".join(answer.split()).casefold()


def validate_with_solver(draft: ExerciseDraft, output: SolverOutput) -> dict:
    expected = {q.id for q in draft.questions}
    supplied = [a.id for a in output.answers]
    protocol_errors = []
    if len(supplied) != len(set(supplied)):
        protocol_errors.append("duplicate_solver_ids")
    if set(supplied) != expected:
        protocol_errors.append("missing_or_unknown_solver_ids")
    answers = {a.id: a for a in output.answers}
    items = {}
    for q in draft.questions:
        answer = answers.get(q.id)
        reasons = list(protocol_errors)
        if answer is None:
            reasons.append("missing_solver_answer")
        else:
            agrees = (
                answer.answer == q.answer
                if q.kind in {"multiple_choice", "matching_headings"}
                else _canonical(answer.answer) == _canonical(q.answer)
            )
            if not agrees:
                reasons.append("solver_answer_mismatch")
            if q.kind == "true_false_not_given":
                if answer.answer not in {"TRUE", "FALSE", "NOT GIVEN"}:
                    reasons.append("invalid_solver_classification")
            if q.kind in {"multiple_choice", "matching_headings"} and answer.answer not in q.options:
                reasons.append("invalid_solver_option")
            is_ng = q.kind == "true_false_not_given" and answer.answer == "NOT GIVEN"
            if is_ng:
                if answer.evidence_span is not None:
                    reasons.append("solver_not_given_has_evidence")
            elif not answer.evidence_span or answer.evidence_span not in draft.text:
                reasons.append("solver_evidence_missing_or_not_verbatim")
            if q.kind == "matching_headings":
                paragraphs, _ = _paragraphs(draft.text)
                if not answer.evidence_span or answer.evidence_span not in paragraphs.get(q.paragraph_id, ""):
                    reasons.append("solver_heading_evidence_outside_target")
            if q.kind == "sentence_completion":
                if not q.word_limit or not 0 < word_count(answer.answer) <= q.word_limit:
                    reasons.append("solver_completion_word_limit")
                if not contains_phrase(draft.text, answer.answer):
                    reasons.append("solver_completion_not_verbatim")
                if not answer.evidence_span or not contains_phrase(answer.evidence_span, answer.answer):
                    reasons.append("solver_completion_not_in_evidence")
            if not answer.reason.strip():
                reasons.append("solver_reason_blank")
        items[q.id] = {
            "passed": not reasons, "reasons": reasons,
            "answer": answer.answer if answer else None,
            "evidence_span": answer.evidence_span if answer else None,
            "reason": answer.reason if answer else None,
        }
    return {"status": "passed" if not protocol_errors else "invalid_protocol", "status_scope": "protocol",
            "all_items_passed": all(item["passed"] for item in items.values()), "protocol_errors": protocol_errors, "items": items}
