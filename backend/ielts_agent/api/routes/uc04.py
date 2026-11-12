"""UC-04 HTTP adapter; generation decisions belong to the agent."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...agents.uc04.agent import UC04Agent
from ...agents.uc04.models import GenerateRequest, QuestionKind


class ExerciseSummary(BaseModel):
    id: UUID
    title: str
    skill: Literal["reading", "listening"]
    topic: str
    target_band: float
    source: str
    status: Literal["verified"]
    created_at: datetime
    question_count: int
    question_types: list[QuestionKind]


class ExerciseList(BaseModel):
    items: list[ExerciseSummary]
    total: int
    limit: int
    offset: int


def create_router(agent: UC04Agent, bank) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["UC-04"])

    @router.post("/exercises", status_code=201)
    def generate(request: GenerateRequest):
        return agent.run(request)

    @router.get("/exercises", response_model=ExerciseList)
    def list_items(
        skill: Literal["reading", "listening"] | None = None,
        target_band: float | None = Query(default=None, ge=1, le=9, multiple_of=0.5),
        q: str = Query(default="", max_length=200, pattern=r"^[^\x00]*$"),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=2147483647),
    ):
        """List published Reading/Listening summaries, newest first."""
        return bank.list_items(skill=skill, target_band=target_band, q=q.strip(), limit=limit, offset=offset)

    @router.get("/exercises/{item_id}")
    def get_item(item_id: UUID):
        item = bank.get_item(str(item_id))
        if item is None:
            raise HTTPException(404, "Exercise not found")
        return item

    @router.get("/exercises/{item_id}/answers")
    def get_answers(item_id: UUID):
        answers = bank.get_answers(str(item_id))
        if answers is None:
            raise HTTPException(404, "Exercise not found")
        return answers

    @router.get("/traces/{trace_id}")
    def get_trace(trace_id: UUID):
        trace = bank.get_trace(str(trace_id))
        if trace is None:
            raise HTTPException(404, "Trace not found")
        return trace

    return router
