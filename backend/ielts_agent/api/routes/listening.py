"""Listening script preparation for downstream speech synthesis."""

from uuid import UUID
import base64
import json

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from ...agents.uc04.listening_turns import ScriptTurns, SplitScriptRequest, split_script
from ...infrastructure.azure_speech import AudioOptions, AzureSpeech, SpeechError, SynthesizeScriptRequest
from ...listening.verification import ListeningAudioVerifier, VerifiedAudio


class _ListeningRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validate(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                # Match the practice API: never reflect invalid script input.
                # Escape even error locations, which may contain Unicode from
                # an unexpected JSON key, so malformed input still returns 422.
                detail = [{key: item[key] for key in ("type", "loc", "msg")} for item in error.errors()]
                return Response(content=json.dumps({"detail": detail}, ensure_ascii=True),
                                status_code=422, media_type="application/json")

        return validate


def create_listening_router(bank, speech: AzureSpeech | None = None, verifier: ListeningAudioVerifier | None = None,
                            publication=None, *, authoring_enabled: bool = True) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["Listening"], route_class=_ListeningRoute)

    def authoring():
        if not authoring_enabled:
            raise HTTPException(503, "Set API_TOKEN to enable private audio authoring and verification")

    def failure(error: SpeechError):
        return Response(content=json.dumps({"error": error.code, "message": str(error)}),
                        status_code=error.status_code, media_type="application/json", headers={"Cache-Control": "no-store"})

    def stored_audio(item_id: str):
        if publication is None:
            raise SpeechError(503, "audio_not_configured", "Stored audio verification is not configured")
        return publication.get_verified(item_id)

    def wav(data: bytes):
        return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store",
                        "Content-Disposition": 'attachment; filename="listening.wav"'})

    def parse(script: str) -> ScriptTurns:
        try:
            return split_script(script)
        except ValueError:
            raise HTTPException(422, "Script is invalid or contains an empty speaker turn") from None

    @router.post("/listening/turns", response_model=ScriptTurns)
    def split(request: SplitScriptRequest):
        return parse(request.script)

    @router.get("/exercises/{item_id}/listening-turns", response_model=ScriptTurns)
    def get_turns(item_id: UUID):
        item = bank.get_item(str(item_id))
        if item is None:
            raise HTTPException(404, "Exercise not found")
        if item.get("skill") != "listening":
            raise HTTPException(422, "Exercise must be a Listening item")
        return parse(item["text"])

    def audio(script: str, options: AudioOptions) -> Response:
        if speech is None:
            raise HTTPException(503, "Azure Speech is not configured")
        try:
            data = speech.synthesize(script, options.voices)
        except SpeechError as error:
            return Response(content=json.dumps({"error": error.code, "message": str(error)}),
                            status_code=error.status_code, media_type="application/json",
                            headers={"Cache-Control": "no-store"})
        return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store",
                        "Content-Disposition": 'attachment; filename="listening.wav"'})

    @router.post("/listening/audio", responses={200: {"content": {"audio/wav": {}}}}, response_class=Response,
                 dependencies=[Depends(authoring)])
    def synthesize(request: SynthesizeScriptRequest):
        return audio(request.script, request)

    @router.post("/exercises/{item_id}/audio", responses={200: {"content": {"audio/wav": {}}}}, response_class=Response,
                 dependencies=[Depends(authoring)])
    def synthesize_item(item_id: UUID, options: AudioOptions = AudioOptions()):
        item = bank.get_item(str(item_id))
        if item is None:
            raise HTTPException(404, "Exercise not found")
        if item.get("skill") != "listening":
            raise HTTPException(422, "Exercise must be a Listening item")
        try:
            if publication is None:
                raise SpeechError(503, "audio_not_configured", "Stored audio verification is not configured")
            result = publication.build(str(item_id), options.voices)
            if result["status"] != "verified":
                raise SpeechError(409, "audio_verification_failed", "Audio was saved for review and cannot be delivered")
            return wav(stored_audio(str(item_id))["audio"])
        except SpeechError as error:
            return failure(error)

    def verify(script: str, options: AudioOptions, response: Response):
        response.headers["Cache-Control"] = "no-store"
        if verifier is None:
            raise HTTPException(503, "Listening audio verification is not configured")
        try:
            return verifier.generate(script, options.voices)
        except SpeechError as error:
            return Response(content=json.dumps({"error": error.code, "message": str(error)}),
                            status_code=error.status_code, media_type="application/json",
                            headers={"Cache-Control": "no-store"})

    @router.post("/listening/audio/verify", response_model=VerifiedAudio, dependencies=[Depends(authoring)])
    def verify_script(request: SynthesizeScriptRequest, response: Response):
        return verify(request.script, request, response)

    @router.post("/exercises/{item_id}/audio/verify", dependencies=[Depends(authoring)])
    def verify_item(item_id: UUID, response: Response, options: AudioOptions = AudioOptions()):
        item = bank.get_item(str(item_id))
        if item is None:
            raise HTTPException(404, "Exercise not found")
        if item.get("skill") != "listening":
            raise HTTPException(422, "Exercise must be a Listening item")
        response.headers["Cache-Control"] = "no-store"
        try:
            if publication is None:
                raise SpeechError(503, "audio_not_configured", "Stored audio verification is not configured")
            result = publication.build(str(item_id), options.voices)
            if result["status"] == "verified":
                result["audio_base64"] = base64.b64encode(stored_audio(str(item_id))["audio"]).decode("ascii")
                result["audio_media_type"] = "audio/wav"
            return result
        except SpeechError as error:
            return failure(error)

    @router.get("/exercises/{item_id}/audio", response_class=Response)
    def download_audio(item_id: UUID):
        try:
            return wav(stored_audio(str(item_id))["audio"])
        except SpeechError as error:
            return failure(error)

    @router.get("/exercises/{item_id}/audio/timings")
    def audio_timings(item_id: UUID, response: Response):
        response.headers["Cache-Control"] = "no-store"
        try:
            record = stored_audio(str(item_id))
            public_fields = ("position", "speaker_id", "start_frame", "end_frame", "start_seconds", "end_seconds",
                             "source_start_char", "source_end_char")
            return {"item_id": str(item_id), "audio_sha256": record["audio_sha256"],
                    "sample_rate": record["manifest"]["sample_rate"],
                    "turns": [{key: turn[key] for key in public_fields} for turn in record["manifest"]["turns"]]}
        except SpeechError as error:
            return failure(error)

    return router
