"""HTTP adapter for Reading/Listening practice; answer keys stay in the service."""

from typing import Annotated
from uuid import UUID
import json

from fastapi import APIRouter, Body, Header, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from ...practice.models import AttemptView, CreatedAttempt, SaveAnswers, SubmitAnswers
from ...practice.service import PracticeService


AttemptToken = Annotated[str | None, Header(alias="X-Attempt-Token", max_length=256)]


class _PracticeRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validate(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                # Avoid reflecting answer text or capability tokens in errors.
                # ASCII escaping also handles malformed Unicode in JSON input.
                detail = [{key: item[key] for key in ("type", "loc", "msg")} for item in error.errors()]
                return Response(content=json.dumps({"detail": detail}, ensure_ascii=True),
                                status_code=422, media_type="application/json",
                                headers={"Cache-Control": "no-store"})

        return validate


def create_practice_router(service: PracticeService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["Reading/Listening practice"], route_class=_PracticeRoute)

    def private(response: Response):
        response.headers["Cache-Control"] = "no-store"

    @router.post("/exercises/{item_id}/attempts", response_model=CreatedAttempt, status_code=201)
    def start(item_id: UUID, response: Response):
        private(response)
        return service.start(str(item_id))

    @router.get("/attempts/{attempt_id}", response_model=AttemptView)
    def get_attempt(attempt_id: UUID, response: Response, token: AttemptToken = None):
        private(response)
        return service.get(str(attempt_id), token)

    @router.patch("/attempts/{attempt_id}/answers", response_model=AttemptView)
    def save_answers(attempt_id: UUID, request: SaveAnswers, response: Response, token: AttemptToken = None):
        private(response)
        return service.save(str(attempt_id), token, {str(key): value for key, value in request.answers.items()})

    @router.post("/attempts/{attempt_id}/submit", response_model=AttemptView)
    def submit(attempt_id: UUID, response: Response,
               request: Annotated[SubmitAnswers | None, Body()] = None, token: AttemptToken = None):
        private(response)
        answers = {} if request is None else {str(key): value for key, value in request.answers.items()}
        return service.submit(str(attempt_id), token, answers)

    return router
