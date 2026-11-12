"""Fail-closed checks of anchored answer evidence against timed lexical STT words."""

from dataclasses import dataclass
import re
from typing import Literal

from pydantic import BaseModel

from ..agents.uc04.listening_turns import split_script
from .comparison import compare_words, words


_SMALL = dict(zip("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20)))
_TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
_ORDINAL = dict(zip("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth".split(), range(1, 20)))
_ORDINAL.update(dict(zip("twentieth thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth".split(), range(20, 100, 10))))
_TOKEN = re.compile(r"[^\W_]+(?:['\u2019\u2018][^\W_]+)*", re.UNICODE)


@dataclass
class Token:
    value: str
    start: float
    end: float
    turn: int = 0


class AnswerCheck(BaseModel):
    question_id: str
    number: int
    question_type: str
    status: Literal["passed", "failed", "unverifiable"]
    reason: str
    reference_start: int | None = None
    reference_end: int | None = None
    expected_start_seconds: float | None = None
    expected_end_seconds: float | None = None
    recognized_excerpt: str = ""


class AnswerVerification(BaseModel):
    delivery_allowed: bool
    checks: list[AnswerCheck]


def _number(tokens: list[Token], index: int, depth: int = 0) -> tuple[str, int] | None:
    """Conservative small English cardinal/ordinal equivalence, not fuzzy matching."""
    value = tokens[index].value
    if depth > 3:
        return None
    ordinal = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", value)
    if value.isdigit() or ordinal:
        digits = ordinal[1] if ordinal else value
        return (digits if len(digits) > 1 and digits.startswith("0") else str(int(digits))), index + 1
    if value in _ORDINAL:
        return str(_ORDINAL[value]), index + 1
    if value not in _SMALL and value not in _TENS:
        return None
    total = _SMALL.get(value, _TENS.get(value, 0))
    end = index + 1
    if value in _TENS and end < len(tokens) and tokens[end].value in {**_SMALL, **_ORDINAL}:
        unit = _SMALL.get(tokens[end].value, _ORDINAL.get(tokens[end].value, 99))
        if 0 < unit < 10:
            total += unit
            end += 1
    if end < len(tokens) and tokens[end].value == "hundred" and 0 < total < 10:
        total *= 100
        end += 1
        rest = end + 1 if end < len(tokens) and tokens[end].value == "and" else end
        if rest < len(tokens) and tokens[rest].value in {**_SMALL, **_TENS}:
            following = _number(tokens, rest, depth + 1)
            if following and int(following[0]) < 100:
                total += int(following[0])
                end = following[1]
    return str(total), end


def canonical(tokens: list[Token]) -> list[Token]:
    result = []
    index = 0
    while index < len(tokens):
        number = _number(tokens, index)
        end = number[1] if number else index + 1
        result.append(Token(number[0] if number else tokens[index].value,
                            tokens[index].start, tokens[end - 1].end, tokens[index].turn))
        index = end
    return result


def _source_tokens(script: str) -> list[Token]:
    result = []
    for turn in split_script(script).turns:
        tokens = []
        for match in _TOKEN.finditer(turn.text):
            for value in words(match[0]):
                tokens.append(Token(value, turn.start_char + match.start(), turn.start_char + match.end(), turn.position))
        result.extend(canonical(tokens))
    return result


def check_answers(script: str, exercise: dict, answers: dict, timings: list, recognition) -> AnswerVerification:
    """Timings come from TTS frame counts; STT offsets are independently observed.

    Whole turn windows are used, not fabricated expected word timestamps. Every
    target must also align to its anchored occurrence in the complete transcript.
    Private keys/evidence are inputs only and are not copied into check output.
    """
    reference = _source_tokens(script)
    recognized = canonical([Token(value, word.start_seconds, word.end_seconds)
                            for word in recognition.words for value in words(word.text)])
    checks = []
    question_list = [(group, question) for group in exercise["question_groups"] for question in group["questions"]]
    keys = {row["question_id"]: row for row in answers.get("answers", [])}
    windows = {turn.position: turn for turn in timings}
    mapping = {}
    edits = []
    if recognized and recognition.complete:
        comparison = compare_words(" ".join(token.value for token in reference), " ".join(token.value for token in recognized))
        edits = comparison.differences
        i = j = 0
        for edit in edits:
            while i < edit.reference_start:
                mapping[i] = j
                i, j = i + 1, j + 1
            i, j = edit.reference_end, edit.transcript_end
        while i < len(reference):
            mapping[i] = j
            i, j = i + 1, j + 1
    for group, question in question_list:
        check = AnswerCheck(question_id=question["id"], number=question["number"],
                            question_type=group["question_type"], status="unverifiable", reason="missing_evidence")
        checks.append(check)
        key = keys.get(question["id"], {})
        evidence = key.get("evidence_span")
        if not isinstance(evidence, str) or not evidence.strip():
            continue
        begin = script.find(evidence)
        if begin < 0 or script.find(evidence, begin + 1) >= 0:
            check.reason = "ambiguous_or_missing_evidence"
            continue
        end = begin + len(evidence)
        indices = [i for i, token in enumerate(reference) if token.start >= begin and token.end <= end]
        if not indices:
            continue
        start, stop = indices[0], indices[-1] + 1
        if group["question_type"] == "sentence_completion":
            target = [token.value for token in canonical([Token(value, 0, 0) for value in words(str(key.get("answer_key", "")))])]
            positions = [i for i in range(start, stop - len(target) + 1)
                         if target and [t.value for t in reference[i:i + len(target)]] == target]
            if len(positions) != 1:
                check.reason = "answer_not_uniquely_anchored"
                continue
        elif group["question_type"] not in {"multiple_choice", "matching_headings", "true_false_not_given"}:
            check.reason = "unsupported_question_type"
            continue
        if group["question_type"] == "true_false_not_given" and str(key.get("answer_key", "")).strip().upper() == "NOT GIVEN":
            check.reason = "no_spoken_evidence_for_not_given"
            continue
        expected_turns = {token.turn for token in reference[start:stop]}
        if not expected_turns or any(position not in windows for position in expected_turns):
            check.reason = "missing_expected_timing"
            continue
        # Keep the whole independently timed context. Narrow key-only matching
        # can accept 'not fifteen', 'fifteen point five', or a wrongly spelled
        # name when the unspelled name was recognized elsewhere in the utterance.
        context = [i for i, token in enumerate(reference) if token.turn in expected_turns]
        start, stop = context[0], context[-1] + 1
        check.reference_start, check.reference_end = start, stop
        check.expected_start_seconds = min(windows[position].start_seconds for position in expected_turns)
        check.expected_end_seconds = max(windows[position].end_seconds for position in expected_turns)
        if not recognized or not recognition.complete:
            check.reason = "missing_complete_word_timing"
            continue
        if any(i not in mapping for i in range(start, stop)) or any(
            edit.kind == "insertion" and start <= edit.reference_start <= stop for edit in edits
        ):
            check.status, check.reason = "failed", "answer_evidence_differs"
            continue
        matched = [recognized[mapping[i]] for i in range(start, stop)]
        check.recognized_excerpt = " ".join(token.value for token in matched)
        if any(token.start < windows[reference[i].turn].start_seconds - 0.15
               or token.end > windows[reference[i].turn].end_seconds + 0.15
               for i, token in zip(range(start, stop), matched)):
            check.status, check.reason = "failed", "answer_outside_expected_turn"
            continue
        check.status, check.reason = "passed", "anchored_answer_matches"
    return AnswerVerification(delivery_allowed=bool(checks) and all(check.status == "passed" for check in checks), checks=checks)
