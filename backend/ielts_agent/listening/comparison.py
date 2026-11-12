"""Bounded, exact word-level Levenshtein alignment for STT review."""

import re
from typing import Literal
import unicodedata

from pydantic import BaseModel


MAX_COMPARISON_WORDS = 2500
MAX_TRANSCRIPT_CHARS = 40_000
_WORDS = re.compile(r"[^\W_]+(?:'[^\W_]+)*", re.UNICODE)


class WordDifference(BaseModel):
    kind: Literal["substitution", "deletion", "insertion"]
    expected: str
    recognized: str
    reference_start: int
    reference_end: int
    transcript_start: int
    transcript_end: int


class TextComparison(BaseModel):
    normalization: str = "nfkc-casefold-words-v1"
    normalized_match: bool
    reference_word_count: int
    transcript_word_count: int
    substitutions: int
    deletions: int
    insertions: int
    word_error_rate: float
    differences: list[WordDifference]


def words(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold().replace("\u2019", "'").replace("\u2018", "'")
    return _WORDS.findall(normalized)


def compare_words(reference: str, transcript: str) -> TextComparison:
    """WER=(substitutions+deletions+insertions)/reference words; may exceed 1.

    Indices in differences refer to normalized token sequences, end exclusive.
    Ties prefer substitution, then deletion, then insertion, deterministically.
    """
    if len(reference) > MAX_TRANSCRIPT_CHARS or len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise ValueError("Comparison text is too long")
    expected, actual = words(reference), words(transcript)
    n, m = len(expected), len(actual)
    if not n or n > MAX_COMPARISON_WORDS or m > MAX_COMPARISON_WORDS:
        raise ValueError("Reference must contain words; comparison is limited to 2500 words per text")
    # One byte per alignment cell plus two distance rows, rather than an int matrix.
    stride = m + 1
    directions = bytearray((n + 1) * stride)
    for j in range(1, m + 1):
        directions[j] = 3
    previous = list(range(m + 1))
    for i, expected_word in enumerate(expected, start=1):
        row = [i] + [0] * m
        offset = i * stride
        directions[offset] = 2
        for j, actual_word in enumerate(actual, start=1):
            equal = expected_word == actual_word
            cost = previous[j - 1] + (not equal)
            direction = 0 if equal else 1
            deletion, insertion = previous[j] + 1, row[j - 1] + 1
            if deletion < cost:
                cost, direction = deletion, 2
            if insertion < cost:
                cost, direction = insertion, 3
            row[j] = cost
            directions[offset + j] = direction
        previous = row
    operations = []
    i, j = n, m
    while i or j:
        direction = directions[i * stride + j]
        if direction < 2:
            operations.append((direction, i - 1, i, j - 1, j))
            i, j = i - 1, j - 1
        elif direction == 2:
            operations.append((direction, i - 1, i, j, j))
            i -= 1
        else:
            operations.append((direction, i, i, j - 1, j))
            j -= 1
    operations.reverse()
    substitutions = sum(op[0] == 1 for op in operations)
    deletions = sum(op[0] == 2 for op in operations)
    insertions = sum(op[0] == 3 for op in operations)
    differences = []
    group = None

    def append_group():
        if group is not None:
            direction, start, end, actual_start, actual_end = group
            differences.append(WordDifference(kind={1: "substitution", 2: "deletion", 3: "insertion"}[direction],
                expected=" ".join(expected[start:end]), recognized=" ".join(actual[actual_start:actual_end]),
                reference_start=start, reference_end=end, transcript_start=actual_start, transcript_end=actual_end))

    for operation in operations:
        direction, start, end, actual_start, actual_end = operation
        if not direction:
            append_group()
            group = None
        elif group is not None and direction == group[0] and start == group[2] and actual_start == group[4]:
            group = (direction, group[1], end, group[3], actual_end)
        else:
            append_group()
            group = operation
    append_group()
    errors = substitutions + deletions + insertions
    return TextComparison(normalized_match=errors == 0, reference_word_count=n, transcript_word_count=m,
                          substitutions=substitutions, deletions=deletions, insertions=insertions,
                          word_error_rate=round(errors / n, 6), differences=differences)
