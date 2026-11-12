"""Deterministic marking of verified, single-answer practice questions.

This module never calls a model. It validates the complete frozen key before
marking any response; malformed snapshots must not produce a partial score.
"""

from dataclasses import dataclass
import unicodedata

from ..agents.uc04.rules import word_count


GRADING_VERSION = "fixed-key-v1"
_KINDS = {"true_false_not_given", "multiple_choice", "sentence_completion", "matching_headings"}
_CLASSIFICATIONS = {"true", "false", "not given"}


def _canonical(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not _canonical(value):
        raise ValueError(f"Snapshot requires nonblank {name}")
    return value


@dataclass(frozen=True)
class _Question:
    id: str
    number: int
    kind: str
    correct_answer: str
    explanation: str
    evidence_span: str | None
    options: frozenset[str]
    max_words: int | None


def _questions(exercise: dict, answer_key: dict) -> list[_Question]:
    if not isinstance(exercise, dict) or not isinstance(answer_key, dict):
        raise ValueError("Exercise and answer key must be snapshot objects")
    item_id = _text(exercise.get("id"), "exercise id")
    if answer_key.get("item_id") != item_id:
        raise ValueError("Answer key does not belong to this exercise")
    groups, answers = exercise.get("question_groups"), answer_key.get("answers")
    if not isinstance(groups, list) or not groups or not isinstance(answers, list):
        raise ValueError("Snapshot requires question groups and an answer list")

    keys = {}
    for answer in answers:
        if not isinstance(answer, dict):
            raise ValueError("Answer key entries must be objects")
        question_id = _text(answer.get("question_id"), "answer question id")
        if question_id in keys:
            raise ValueError("Duplicate answer key question id")
        keys[question_id] = answer

    result = []
    seen_ids, seen_numbers = set(), set()
    for group in groups:
        if (not isinstance(group, dict) or not isinstance(group.get("question_type"), str)
                or group["question_type"] not in _KINDS):
            raise ValueError("Unsupported question type in snapshot")
        kind = group["question_type"]
        questions = group.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ValueError("Question groups must contain questions")
        for question in questions:
            if not isinstance(question, dict):
                raise ValueError("Snapshot questions must be objects")
            question_id = _text(question.get("id"), "question id")
            number = question.get("number")
            if type(number) is not int or number < 1 or number > 40 or number in seen_numbers:
                raise ValueError("Question numbers must be unique integers from 1 to 40")
            if question_id in seen_ids or question_id not in keys:
                raise ValueError("Duplicate question id or missing answer key")
            if question.get("excluded"):
                raise ValueError("Excluded questions cannot be graded automatically")
            seen_ids.add(question_id)
            seen_numbers.add(number)
            answer = keys[question_id]
            if type(answer.get("number")) is not int or answer["number"] != number:
                raise ValueError("Answer key question number mismatch")
            correct = _text(answer.get("answer_key"), "correct answer")
            explanation = _text(answer.get("explanation"), "answer explanation")
            evidence = answer.get("evidence_span")
            if evidence is not None and not isinstance(evidence, str):
                raise ValueError("Answer evidence must be text or null")

            labels = frozenset()
            max_words = None
            if kind in {"multiple_choice", "matching_headings"}:
                options = question.get("options") or group.get("options")
                if not isinstance(options, dict) or not options:
                    raise ValueError("Option questions require an option bank")
                canonical_labels = [_canonical(_text(label, "option label")) for label in options]
                for value in options.values():
                    _text(value, "option text")
                labels = frozenset(canonical_labels)
                if len(labels) != len(options) or _canonical(correct) not in labels:
                    raise ValueError("Option labels must be distinct and contain the correct answer")
            elif kind == "true_false_not_given":
                if _canonical(correct) not in _CLASSIFICATIONS:
                    raise ValueError("Invalid classification in answer key")
            else:
                limits = group.get("response_limits")
                max_words = limits.get("max_words") if isinstance(limits, dict) else None
                if type(max_words) is not int or max_words < 1:
                    raise ValueError("Completion questions require a positive max_words limit")
                if not 0 < word_count(_canonical(correct)) <= max_words:
                    raise ValueError("Completion answer key exceeds its word limit")
            result.append(_Question(question_id, number, kind, correct, explanation, evidence, labels, max_words))
    if seen_ids != keys.keys():
        raise ValueError("Answer key contains questions outside the exercise")
    return result


def validate_exercise(exercise: dict, answer_key: dict) -> None:
    """Reject a snapshot that could not be fully graded at submission time."""
    _questions(exercise, answer_key)


def grade(exercise: dict, answer_key: dict, responses: dict[str, str]) -> dict:
    """Mark every answer slot against its frozen verified key.

    Case, Unicode compatibility and whitespace are normalized. Spelling,
    punctuation and option labels remain significant. Missing/blank answers
    receive zero; each question can contribute at most one point.
    """
    questions = _questions(exercise, answer_key)
    if not isinstance(responses, dict) or any(not isinstance(value, str) for value in responses.values()):
        raise ValueError("Responses must map question ids to text")
    if responses.keys() - {question.id for question in questions}:
        raise ValueError("Response question does not belong to this exercise")

    details = []
    for question in questions:
        response = responses.get(question.id, "")
        normalized = _canonical(response)
        if not normalized:
            reason = "unanswered"
        elif question.kind == "sentence_completion" and word_count(normalized) > question.max_words:
            reason = "word_limit_exceeded"
        elif question.kind in {"multiple_choice", "matching_headings"} and normalized not in question.options:
            reason = "invalid_option"
        elif question.kind == "true_false_not_given" and normalized not in _CLASSIFICATIONS:
            reason = "invalid_classification"
        else:
            reason = "correct" if normalized == _canonical(question.correct_answer) else "incorrect"
        details.append({
            "question_id": question.id,
            "number": question.number,
            "question_type": question.kind,
            "response": response,
            "correct_answer": question.correct_answer,
            "is_correct": reason == "correct",
            "reason": reason,
            "explanation": question.explanation,
            "evidence_span": question.evidence_span,
        })

    total = len(details)
    raw_score = sum(detail["is_correct"] for detail in details)
    unanswered = sum(detail["reason"] == "unanswered" for detail in details)
    return {
        "grading_version": GRADING_VERSION,
        "raw_score": raw_score,
        "total_questions": total,
        "answered_questions": total - unanswered,
        "wrong_count": total - unanswered - raw_score,
        "unanswered_count": unanswered,
        "percentage": round(raw_score * 100 / total, 2),
        "band": None,
        "band_reason": "partial_practice",
        "questions": details,
    }
