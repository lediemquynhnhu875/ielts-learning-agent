"""Deterministic labelled-script segmentation; no speaker inference or TTS calls."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_SCRIPT_LENGTH = 100_000
_ROLES = (
    "Narrator", "Receptionist", "Caller", "Man", "Woman", "Interviewer",
    "Interviewee", "Tutor", "Lecturer", "Professor", "Student", "Guide",
    "Customer", "Agent", "Assistant", "Librarian", "Advisor", "Adviser",
    "Speaker", "Clerk", "Presenter", "Host", "Guest",
)
_ROLE_PATTERN = "(?:" + "|".join(_ROLES) + r")(?:[ \t]+(?:[0-9]+|[A-Z]))?"
_ROLE_LABEL = re.compile(r"(?<!\S)(?P<label>" + _ROLE_PATTERN + r")[ \t]*:", re.IGNORECASE)
# Names are accepted at line starts; common headings are reserved for prose.
_NAME_LABEL = re.compile(
    r"(?:^|(?<=\r))[ \t]*(?P<label>[A-Z][a-z]*(?:[-'][A-Z]?[a-z]+)*(?:[ \t]+[A-Z][a-z]+){0,2})[ \t]*:",
    re.MULTILINE,
)
_HEADINGS = {"note", "notes", "section", "part", "introduction", "script", "transcript", "title", "example", "time", "warning", "summary", "instructions"}


class SplitScriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    script: str = Field(min_length=1, max_length=MAX_SCRIPT_LENGTH, strict=True)

    @field_validator("script")
    @classmethod
    def require_speech(cls, value: str) -> str:
        if not value.strip() or "\x00" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Script must contain valid nonblank text")
        return value


class Speaker(BaseModel):
    id: str
    label: str


class SpeakerTurn(BaseModel):
    position: int
    speaker_id: str
    text: str
    start_char: int
    end_char: int


class ScriptTurns(BaseModel):
    speakers: list[Speaker]
    turns: list[SpeakerTurn]


def split_script(script: str) -> ScriptTurns:
    """Split explicit labels, preserving exact speech slices and turn boundaries.

    Common roles work inline; names must first occur at a line start. Unlabelled
    text is Narrator speech. Offsets are Python Unicode character indices into
    the original input (end exclusive), never a rewritten/normalized script.
    """
    script = SplitScriptRequest(script=script).script
    markers = {m.start("label"): m for m in _ROLE_LABEL.finditer(script)}
    names: dict[str, str] = {}
    for match in _NAME_LABEL.finditer(script):
        name = " ".join(match.group("label").split())
        if name.casefold() not in _HEADINGS:
            markers.setdefault(match.start("label"), match)
            names.setdefault(name.casefold(), name)
    if names:
        alternatives = [r"[ \t]+".join(re.escape(word) for word in name.split()) for name in names.values()]
        pattern = re.compile(r"(?<!\S)(?P<label>" + "|".join(alternatives) + r")[ \t]*:", re.IGNORECASE)
        for match in pattern.finditer(script):
            markers.setdefault(match.start("label"), match)

    speakers: dict[str, Speaker] = {}
    turns = []

    def append(label: str, start: int, end: int, *, required: bool = False):
        while start < end and script[start].isspace():
            start += 1
        while end > start and script[end - 1].isspace():
            end -= 1
        if start >= end:
            if required:
                raise ValueError("Each speaker label must be followed by speech")
            return
        label = " ".join(label.split())
        key = label.casefold()
        if key not in speakers:
            speakers[key] = Speaker(id=f"speaker_{len(speakers) + 1}", label=label)
        turns.append(SpeakerTurn(position=len(turns) + 1, speaker_id=speakers[key].id,
                                 text=script[start:end], start_char=start, end_char=end))

    # A compound label such as "Travel Agent:" contains the inline role
    # "Agent:". Keep the whole label, never overlapping/negative speech spans.
    ordered = []
    for start, marker in sorted(markers.items()):
        if not ordered or start >= ordered[-1][1].end():
            ordered.append((start, marker))
    append("Narrator", 0, ordered[0][0] if ordered else len(script))
    for index, (_, marker) in enumerate(ordered):
        end = ordered[index + 1][0] if index + 1 < len(ordered) else len(script)
        append(marker.group("label"), marker.end(), end, required=True)
    return ScriptTurns(speakers=list(speakers.values()), turns=turns)
