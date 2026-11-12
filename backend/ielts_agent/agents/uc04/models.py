"""UC-04 agent contracts and an explicit answer-free solver projection.

These are transient generation contracts. Persisted Reading/Listening data uses
CONTENT_ITEM -> QUESTION_GROUP -> QUESTION (see DATABASE_CONTEXT.md).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


QuestionKind = Literal[
    "true_false_not_given",
    "multiple_choice",
    "sentence_completion",
    "matching_headings",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerateRequest(Contract):
    skill: Literal["reading", "listening"]
    topic: str = Field(min_length=3, max_length=200)
    target_band: float = Field(ge=1, le=9)
    question_count: int = Field(default=10, ge=8, le=13)
    completion_word_limit: int = Field(default=2, ge=1, le=5)

    @field_validator("topic", mode="before")
    @classmethod
    def strip_topic(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("target_band")
    @classmethod
    def half_band_steps(cls, value: float) -> float:
        if not (value * 2).is_integer():
            raise ValueError("target_band must use half-band steps")
        return value


class PublicQuestion(Contract):
    id: str = Field(min_length=1, max_length=40)
    kind: QuestionKind
    prompt: str = Field(min_length=1)
    options: dict[str, str] = Field(default_factory=dict)
    word_limit: int | None = None
    paragraph_id: str | None = None

    @field_validator("id", "prompt")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class Question(PublicQuestion):
    answer: str = Field(min_length=1)
    evidence_span: str | None = None
    explanation: str = Field(min_length=1)

    @field_validator("answer", "explanation")
    @classmethod
    def require_nonblank_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    def public(self) -> PublicQuestion:
        # Deliberate allowlist: never serialize the full Question and subtract
        # secrets, because a future answer-related field could then leak.
        return PublicQuestion(
            id=self.id,
            kind=self.kind,
            prompt=self.prompt,
            options=dict(self.options),
            word_limit=self.word_limit,
            paragraph_id=self.paragraph_id,
        )


class ExerciseDraft(Contract):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    questions: list[Question] = Field(max_length=30)


class SolverAnswer(Contract):
    id: str = Field(min_length=1, max_length=40)
    answer: str = Field(min_length=1)
    evidence_span: str | None = None
    reason: str = Field(min_length=1)


class SolverOutput(Contract):
    answers: list[SolverAnswer] = Field(max_length=30)


class SafetyDecision(Contract):
    allowed: StrictBool
    reason: str = Field(min_length=1)
