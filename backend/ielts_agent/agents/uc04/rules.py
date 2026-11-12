"""UC-04 agent's deterministic tools; semantics belong to the blind solver."""

from collections import Counter
from dataclasses import dataclass, field
import re

from .models import ExerciseDraft, GenerateRequest, Question


# Hyphenated words and contractions are one word, as are numeric values such as
# 1,000 and 3.5. Unicode letters allow Vietnamese place names without corruption.
_WORD = re.compile(r"[^\W_]+(?:[-\u2019'][^\W_]+)*(?:[.,]\d+)*", re.UNICODE)
_PARAGRAPH = re.compile(r"^\[([A-Z])\][ \t]*$", re.MULTILINE)


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def contains_phrase(text: str, phrase: str) -> bool:
    """Require an exact quote that does not split a word counted by _WORD."""
    if not phrase:
        return False
    inside_words = {
        position
        for word in _WORD.finditer(text)
        for position in range(word.start() + 1, word.end())
    }
    # A lookahead checks every occurrence, including overlapping ones. Keep
    # the existing \w checks so underscores cannot create new word boundaries.
    pattern = r"(?<!\w)(?=" + re.escape(phrase) + r"(?!\w))"
    for match in re.finditer(pattern, text):
        start = match.start()
        end = start + len(phrase)
        if start not in inside_words and end not in inside_words:
            return True
    return False


@dataclass
class RuleReport:
    exercise_errors: list[str] = field(default_factory=list)
    items: dict[str, list[str]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.exercise_errors and not any(self.items.values())


def _paragraphs(text: str) -> tuple[dict[str, str], bool]:
    markers = list(_PARAGRAPH.finditer(text))
    result: dict[str, str] = {}
    duplicate = False
    for index, marker in enumerate(markers):
        label = marker.group(1)
        duplicate |= label in result
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        result[label] = text[marker.end():end]
    return result, duplicate


def _choice_errors(question: Question) -> list[str]:
    errors = []
    if len(question.options) < 3:
        errors.append("options_require_at_least_three")
    if any(not key.strip() or not value.strip() for key, value in question.options.items()):
        errors.append("options_must_be_nonblank")
    values = [" ".join(value.split()).casefold() for value in question.options.values()]
    if len(values) != len(set(values)):
        errors.append("options_must_be_distinct")
    if question.answer not in question.options:
        errors.append("answer_not_in_options")
    return errors


def validate_rules(
    draft: ExerciseDraft,
    request: GenerateRequest,
    enforce_requested_count: bool = False,
) -> RuleReport:
    report = RuleReport()
    length = word_count(draft.text)
    lower, upper = (600, 900) if request.skill == "reading" else (400, 700)
    if not lower <= length <= upper:
        report.exercise_errors.append(f"text_word_count:{length};expected:{lower}-{upper}")
    count = len(draft.questions)
    if not 8 <= count <= 13:
        report.exercise_errors.append(f"question_count:{count};expected:8-13")
    if enforce_requested_count and count != request.question_count:
        report.exercise_errors.append(f"requested_question_count:{request.question_count};actual:{count}")
    if len({question.kind for question in draft.questions}) < 3:
        report.exercise_errors.append("at_least_three_question_types_required")
    id_counts = Counter(question.id for question in draft.questions)
    if len(id_counts) != count:
        report.exercise_errors.append("duplicate_question_ids")

    paragraphs, duplicate_markers = _paragraphs(draft.text)
    previous_heading_bank = None
    used_headings = set()
    for question in draft.questions:
        errors = report.items.setdefault(question.id, [])
        if id_counts[question.id] > 1 and "duplicate_question_id" not in errors:
            errors.append("duplicate_question_id")
        is_ng = question.kind == "true_false_not_given" and question.answer == "NOT GIVEN"
        if is_ng:
            # No quoted span can establish absence. A separate blind solver must
            # still establish that the statement is neither supported nor denied.
            if question.evidence_span is not None:
                errors.append("not_given_requires_null_evidence")
        elif not question.evidence_span or not question.evidence_span.strip():
            errors.append("evidence_required")
        elif question.evidence_span not in draft.text:
            errors.append("evidence_not_in_text")

        if question.kind != "sentence_completion" and question.word_limit is not None:
            errors.append("word_limit_only_for_completion")
        if question.kind != "matching_headings" and question.paragraph_id is not None:
            errors.append("paragraph_id_only_for_matching_headings")
        if question.kind not in {"multiple_choice", "matching_headings"} and question.options:
            errors.append("options_not_allowed_for_this_type")

        if question.kind == "true_false_not_given":
            if question.answer not in {"TRUE", "FALSE", "NOT GIVEN"}:
                errors.append("invalid_true_false_not_given_answer")
        elif question.kind == "sentence_completion":
            if question.word_limit is None or question.word_limit != request.completion_word_limit:
                errors.append("completion_word_limit_must_match_request")
            if question.word_limit is not None and word_count(question.answer) > question.word_limit:
                errors.append("completion_answer_exceeds_word_limit")
            if word_count(question.answer) == 0:
                errors.append("completion_answer_requires_words")
            if not contains_phrase(draft.text, question.answer):
                errors.append("completion_answer_not_verbatim_in_text")
            if not question.evidence_span or not contains_phrase(question.evidence_span, question.answer):
                errors.append("completion_answer_not_in_evidence")
            if re.findall(r"_{2,}", question.prompt) != ["____"]:
                errors.append("completion_requires_one_four_underscore_blank")
        elif question.kind == "multiple_choice":
            errors.extend(_choice_errors(question))
        elif question.kind == "matching_headings":
            errors.extend(_choice_errors(question))
            label = question.paragraph_id
            if not label or not re.fullmatch(r"[A-Z]", label) or label not in paragraphs:
                errors.append("matching_paragraph_not_found")
            elif question.evidence_span and question.evidence_span not in paragraphs[label]:
                errors.append("matching_evidence_not_in_target_paragraph")
            if duplicate_markers:
                errors.append("matching_paragraph_labels_must_be_unique")
        # Shared heading banks explicitly disallow reusing a heading. Other
        # option types (e.g. MC) may correctly use label A several times.
        heading_bank = tuple(sorted(question.options.items())) if question.kind == "matching_headings" else None
        if heading_bank is not None:
            if heading_bank != previous_heading_bank:
                used_headings = set()
            if question.answer in used_headings:
                errors.append("matching_heading_cannot_be_reused")
            used_headings.add(question.answer)
        previous_heading_bank = heading_bank
    return report
