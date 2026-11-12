"""HTTP contracts for independent, single-content-item practice attempts."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


ResponseText = Annotated[StrictStr, Field(max_length=2000)]


class SaveAnswers(Contract):
    answers: dict[UUID, ResponseText | None] = Field(max_length=40)

    @field_validator("answers", mode="before")
    @classmethod
    def reject_duplicate_uuid_spellings(cls, value):
        # UUID keys are canonicalized by Pydantic. Reject aliases instead of
        # silently overwriting an answer when two spellings refer to one UUID.
        if isinstance(value, dict):
            parsed = []
            for key in value:
                try:
                    parsed.append(UUID(str(key)))
                except (ValueError, TypeError, AttributeError):
                    continue  # Pydantic supplies the normal key validation error.
            if len(parsed) != len(set(parsed)):
                raise ValueError("Duplicate question IDs")
        return value

    @field_validator("answers")
    @classmethod
    def require_storable_text(cls, value):
        for response in value.values():
            if response is None:
                continue
            if "\x00" in response:
                raise ValueError("Responses cannot contain null characters")
        return value


class SubmitAnswers(SaveAnswers):
    answers: dict[UUID, ResponseText | None] = Field(default_factory=dict, max_length=40)


class QuestionResult(Contract):
    question_id: UUID
    number: int
    question_type: Literal[
        "true_false_not_given", "multiple_choice", "sentence_completion", "matching_headings"
    ]
    response: str
    correct_answer: str
    is_correct: bool
    reason: Literal[
        "correct", "unanswered", "word_limit_exceeded", "invalid_option",
        "invalid_classification", "incorrect"
    ]
    explanation: str
    evidence_span: str | None


class PracticeResult(Contract):
    grading_version: str
    raw_score: int
    total_questions: int
    answered_questions: int
    wrong_count: int
    unanswered_count: int
    percentage: float
    band: None = None
    band_reason: Literal["partial_practice"]
    questions: list[QuestionResult]


class AttemptView(Contract):
    attempt_id: UUID
    item_id: UUID
    skill: Literal["reading", "listening"]
    status: Literal["in_progress", "submitted"]
    started_at: datetime
    submitted_at: datetime | None
    elapsed_seconds: int
    exercise: dict
    answers: dict[UUID, str]
    result: PracticeResult | None


class CreatedAttempt(AttemptView):
    attempt_token: str
