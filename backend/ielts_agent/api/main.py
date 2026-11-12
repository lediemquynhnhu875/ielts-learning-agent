"""Local REST entrypoint; apply pending database migrations before serving."""

from contextlib import asynccontextmanager
import secrets

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
import psycopg

from ..infrastructure.db.bank import Bank, BankNotInitializedError
from ..infrastructure.db.practice import PostgresAttemptStore
from ..infrastructure.db.migrations import MigrationError
from ..infrastructure.azure_speech import AzureSpeech
from ..infrastructure.azure_stt import AzureSTT
from ..listening.verification import ListeningAudioVerifier
from ..listening.publication import AudioPublicationService
from ..infrastructure.db.listening_audio import ListeningAudioStore
from ..core.config import Settings
from ..bootstrap import build_uc04_agents
from ..agents.uc04.agent import GenerationError, UC04Agent
from .routes.uc04 import create_router
from .routes.practice import create_practice_router
from .routes.listening import create_listening_router
from ..practice.service import PracticeError, PracticeService


def create_app(*, settings: Settings | None = None, bank=None, agents=None, attempt_store=None, speech=None, audio_verifier=None, audio_publication=None) -> FastAPI:
    settings = settings or Settings.from_env()
    bank = bank if bank is not None else Bank(settings.database_url)
    agents = agents if agents is not None else build_uc04_agents(settings)
    agent = UC04Agent(bank, agents)
    attempt_store = attempt_store if attempt_store is not None else PostgresAttemptStore(bank)

    @asynccontextmanager
    async def lifespan(app):
        try:
            if settings.database_auto_migrate:
                try:
                    await run_in_threadpool(bank.initialize)
                except (psycopg.Error, BankNotInitializedError, MigrationError, OSError):
                    raise RuntimeError(
                        "Automatic PostgreSQL migration failed. Check database availability and migration files; "
                        "run python -m ielts_agent.infrastructure.db.cli init for details."
                    ) from None
            yield
        finally:
            if hasattr(agents, "close"):
                agents.close()

    app = FastAPI(title="IELTS Learning Agent — UC-04", version="0.1.0", lifespan=lifespan)
    bearer = HTTPBearer(auto_error=False)

    def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if settings.api_token and (credentials is None or not secrets.compare_digest(credentials.credentials, settings.api_token)):
            raise HTTPException(401, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"})

    @app.exception_handler(GenerationError)
    async def generation_error(_request, exc: GenerationError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": str(exc), "trace_id": exc.trace_id})

    @app.exception_handler(PracticeError)
    async def practice_error(_request, exc: PracticeError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": str(exc)},
                            headers={"Cache-Control": "no-store"})

    @app.exception_handler(BankNotInitializedError)
    @app.exception_handler(psycopg.Error)
    async def database_error(_request, _exc):
        return JSONResponse(status_code=503, content={"error": "database_unavailable", "message": "PostgreSQL chưa sẵn sàng hoặc schema UC-04 chưa được khởi tạo."})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(create_router(agent, bank), dependencies=[Depends(authenticate)])
    app.include_router(create_practice_router(PracticeService(attempt_store)), dependencies=[Depends(authenticate)])
    speech_service = speech if speech is not None else AzureSpeech(settings)
    transcriber = AzureSTT(settings)
    verifier = audio_verifier if audio_verifier is not None else ListeningAudioVerifier(speech_service, transcriber)
    publication = audio_publication if audio_publication is not None else AudioPublicationService(ListeningAudioStore(bank), speech_service, transcriber)
    app.include_router(create_listening_router(bank, speech_service, verifier, publication, authoring_enabled=bool(settings.api_token)),
                       dependencies=[Depends(authenticate)])
    return app


app = create_app()
