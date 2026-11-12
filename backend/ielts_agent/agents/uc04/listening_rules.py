"""Listening-only rule checks for UC-04 drafts (task l3).

Complements the shared ``rules.validate_rules`` (length, verbatim evidence, word
limits). Checks here only matter for a spoken script:

* Rule A, answer order: the answers must come up in the script in question order.
* Rule B, proper names: a name the learner has to write down must be spelled out
  in the script, and the spelled letters must match the answer key.

Everything is rule-based and deterministic. Thresholds and word lists are
module-level data so they can be tuned without touching the logic.
"""

from dataclasses import dataclass, field
import re

from .models import ExerciseDraft, GenerateRequest, Question
from .rules import RuleReport, contains_phrase


# --------------------------------------------------------------------- data

# A completion answer is a CONFIRMED name once it shows this many signals
# (capitalised / weak prompt cue / spelling cue in the script), or one strong
# prompt cue. A single signal makes it UNCERTAIN.
CONFIRM_THRESHOLD = 2

# Characters around the evidence span in which spelled letters are looked for.
SPELLING_WINDOW_CHARS = 200

# Prompt words that almost always mean the learner writes a spelled name.
STRONG_PROMPT_CUES = ("surname", "family name", "last name", "first name", "street", "road", "avenue")
# Prompt words that make a name likely, but only count as one signal.
WEAK_PROMPT_CUES = ("name", "company", "called", "named")

# Names a listener can write without hearing letters. Lowercase; an answer is
# familiar when the whole phrase, or every word of it, is listed.
FAMILIAR_NAMES: frozenset[str] = frozenset(
    {
        # days and months
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        # countries
        "vietnam", "england", "scotland", "wales", "ireland", "france", "germany", "spain",
        "italy", "china", "japan", "korea", "india", "thailand", "singapore", "malaysia",
        "indonesia", "australia", "canada", "america", "brazil", "mexico", "russia", "egypt",
        "turkey", "greece", "new zealand", "united kingdom", "united states", "south korea",
        # cities
        "london", "paris", "rome", "madrid", "berlin", "tokyo", "beijing", "shanghai",
        "bangkok", "sydney", "melbourne", "toronto", "vancouver", "manchester", "liverpool",
        "birmingham", "edinburgh", "dublin", "new york", "los angeles", "chicago", "boston",
        "hanoi", "saigon", "hue", "da nang", "hoi an", "hai phong", "can tho", "nha trang",
        "ho chi minh city", "hong kong", "kuala lumpur", "seoul", "delhi", "mumbai",
        # very common surnames
        "smith", "jones", "brown", "taylor", "wilson", "davies", "evans", "thomas", "johnson",
        "roberts", "walker", "wright", "robinson", "thompson", "white", "hughes", "edwards",
        "green", "harris", "martin", "jackson", "clarke", "clark", "lewis", "lee", "king",
        "baker", "turner", "miller", "davis", "anderson",
    }
)

# Statuses recorded per completion question in ``ListeningReport.name_checks``.
CONFIRMED = "confirmed"
UNCERTAIN = "uncertain"
EXEMPT = "exempt"
NOT_APPLICABLE = "not_applicable"


# ----------------------------------------------------------------- patterns

_LETTER = r"(?:double[\s-]+[A-Za-z]|[A-Za-z])"
# "H-A-R-T", "H, A, R, T", "h - a - r - t", "C-A-M-P-B-E-double L"
_SEPARATED_SPELLING = re.compile(
    rf"(?<![\w-]){_LETTER}(?:\s*[-,]\s*{_LETTER}){{2,}}(?![\w-])", re.IGNORECASE
)
# "H A R T": plain spaces are only trusted for capital letters.
_SPACED_SPELLING = re.compile(r"(?<!\w)[A-Z](?:[ \t]+[A-Z]){2,}(?!\w)")
_SPELLING_CUE = re.compile(r"\b(?:spell(?:ed|t|ing)?)\b", re.IGNORECASE)
_LETTER_TOKEN = re.compile(_LETTER, re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)


@dataclass
class ListeningReport:
    exercise_errors: list[str] = field(default_factory=list)
    items: dict[str, list[str]] = field(default_factory=dict)
    # Non-blocking notes for the trace (e.g. a name we are unsure about).
    warnings: dict[str, list[str]] = field(default_factory=dict)
    # Completion question id -> confirmed / uncertain / exempt / not_applicable.
    name_checks: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.exercise_errors and not any(self.items.values())


@dataclass(frozen=True)
class _Spelled:
    start: int
    end: int
    letters: str  # lowercase letters only, "double X" expanded


# ------------------------------------------------------------------ helpers


def _letters_only(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.casefold())


def _find_spellings(text: str) -> list[_Spelled]:
    found: list[_Spelled] = []
    taken: list[tuple[int, int]] = []
    for pattern in (_SEPARATED_SPELLING, _SPACED_SPELLING):
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in taken):
                continue
            taken.append((match.start(), match.end()))
            letters = ""
            for token in _LETTER_TOKEN.findall(match.group()):
                letter = token[-1].lower()
                letters += letter * (2 if token.lower().startswith("double") else 1)
            found.append(_Spelled(match.start(), match.end(), letters))
    return found


def _has_cue(prompt: str, cues: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(cue)}\b", prompt, re.IGNORECASE) for cue in cues)


def _is_familiar(answer: str) -> bool:
    words = [word.casefold() for word in _WORD.findall(answer)]
    if not words:
        return False
    return " ".join(words) in FAMILIAR_NAMES or all(word in FAMILIAR_NAMES for word in words)


def _evidence_range(text: str, question: Question) -> tuple[int, int] | None:
    if question.evidence_span:
        start = text.find(question.evidence_span)
        if start != -1:
            return start, start + len(question.evidence_span)
    match = re.search(r"(?<!\w)" + re.escape(question.answer) + r"(?!\w)", text)
    return (match.start(), match.end()) if match else None


# -------------------------------------------------------------------- rules


def _check_answer_order(draft: ExerciseDraft, report: ListeningReport) -> None:
    previous = None
    for question in draft.questions:
        if not question.evidence_span:
            continue  # NOT GIVEN has no evidence; the shared rules cover the rest
        position = draft.text.find(question.evidence_span)
        if position == -1:
            continue  # evidence_not_in_text is the shared rules' finding
        if previous is not None and position < previous:
            report.items[question.id].append("listening_answer_order_violation")
        previous = position


def _check_names(draft: ExerciseDraft, report: ListeningReport) -> None:
    text = draft.text
    spellings = _find_spellings(text)
    completions = [q for q in draft.questions if q.kind == "sentence_completion"]
    answer_letters = {q.id: _letters_only(q.answer) for q in completions}

    for question in completions:
        if not contains_phrase(text, question.answer):
            continue  # completion_answer_not_verbatim_in_text is the shared rules' finding
        span = _evidence_range(text, question)
        if span is None:
            continue
        low = max(0, span[0] - SPELLING_WINDOW_CHARS)
        high = span[1] + SPELLING_WINDOW_CHARS
        window = text[low:high]
        nearby = [s for s in spellings if s.start < high and low < s.end]
        # Letters that spell another question's answer are not evidence about this one.
        own = _letters_only(question.answer)
        others = {letters for qid, letters in answer_letters.items() if qid != question.id}
        relevant = [s for s in nearby if s.letters == own or s.letters not in others]
        matches = any(s.letters == own for s in relevant)

        strong = _has_cue(question.prompt, STRONG_PROMPT_CUES)
        # The answer must appear verbatim in the script, so a capitalised key
        # means a capitalised mention there as well: one signal.
        signals = 0
        signals += question.answer[:1].isupper()
        signals += _has_cue(question.prompt, WEAK_PROMPT_CUES)
        signals += bool(_SPELLING_CUE.search(window))

        if strong or signals >= CONFIRM_THRESHOLD:
            status = CONFIRMED
        elif signals == 1:
            status = UNCERTAIN
        else:
            status = NOT_APPLICABLE
        # Familiar names need no spelling, unless letters are actually spelled out.
        if status in (CONFIRMED, UNCERTAIN) and _is_familiar(question.answer) and not relevant:
            status = EXEMPT
        report.name_checks[question.id] = status

        errors = report.items[question.id]
        if status == NOT_APPLICABLE or matches:
            continue
        if relevant:
            errors.append("listening_spelling_mismatch")
        elif status == CONFIRMED:
            errors.append("listening_name_not_spelled")
        elif status == UNCERTAIN:
            report.warnings.setdefault(question.id, []).append("listening_name_unsure")


def validate_listening_rules(draft: ExerciseDraft) -> ListeningReport:
    """Run the Listening-only checks on a draft whose skill is ``listening``."""
    report = ListeningReport(items={question.id: [] for question in draft.questions})
    _check_answer_order(draft, report)
    _check_names(draft, report)
    return report


def apply_listening_rules(
    draft: ExerciseDraft, request: GenerateRequest, report: RuleReport
) -> dict | None:
    """Fold Listening findings into the shared rule report.

    Item errors land in ``report.items`` so the generation paths drop those
    questions exactly as they do for any other rule failure. Returns the extra
    trace details (warnings, name checks), or None for Reading.
    """
    if request.skill != "listening":
        return None
    listening = validate_listening_rules(draft)
    for question_id, errors in listening.items.items():
        if errors:
            report.items.setdefault(question_id, []).extend(errors)
    return {"warnings": listening.warnings, "name_checks": listening.name_checks}
