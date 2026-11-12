"""Stored Listening audio remains blocked until every timed answer check passes."""

from copy import deepcopy
import hashlib

from fastapi.testclient import TestClient
import pytest

from ielts_agent.agents.uc04.listening_turns import split_script
from ielts_agent.api.main import create_app
from ielts_agent.core.config import Settings
from ielts_agent.infrastructure.azure_speech import SpeechError, TimedSpeech
from ielts_agent.infrastructure.db.listening_audio import config_hash
from ielts_agent.listening.publication import AudioPublicationService
from .test_answer_checking import exercise_and_answers, measured_turns, recognized_turns
from .test_api import ApiBank, AUTH, TOKEN
from .test_azure_speech import wav_audio
from .test_pipeline import FakeAgents, practice_draft


SCRIPT = "Man: The fee is fifteen pounds.\nWoman: Thank you."


class PreviewPublication:
    """API-only stand-in; full service verification is exercised separately below."""

    def __init__(self, audio=None):
        self.audio = wav_audio() if audio is None else audio
        self.calls = []

    def build(self, item_id, voices=None):
        self.calls.append((item_id, voices))
        return {"item_id": item_id, "status": "verified", "verification": {"delivery_allowed": True}}

    def get_verified(self, item_id):
        return {"audio": self.audio}


class MemoryAudioStore:
    def __init__(self, source):
        self.source = deepcopy(source)
        self.record = None
        self.loads = 0
        self.saves = []
        self.change_during_build = False

    def load_source(self, item_id):
        self.loads += 1
        if self.change_during_build and self.loads == 2:
            self.source[0]["text"] += " Changed."
        if self.source is None or self.source[0]["id"] != item_id:
            return None
        return deepcopy(self.source)

    def save(self, item_id, source_binding, config_binding, audio, manifest, verification, status):
        self.record = {"item_id": item_id, "source_hash": source_binding, "config_hash": config_binding,
                       "audio": audio, "audio_sha256": hashlib.sha256(audio).hexdigest(),
                       "manifest": deepcopy(manifest), "verification": deepcopy(verification), "status": status}
        self.saves.append(deepcopy(self.record))
        return deepcopy(self.record)

    def get(self, item_id):
        return deepcopy(self.record)


class TimedSpeechStub:
    def __init__(self, *, invalid_manifest=False):
        self.settings = Settings()
        self.calls = []
        self.invalid_manifest = invalid_manifest

    def synthesize_timed(self, script, voices=None):
        self.calls.append((script, voices))
        turns = measured_turns(script, seconds_per_turn=2)
        if self.invalid_manifest:
            turns[0].start_frame = 5
        speakers = split_script(script).speakers
        return TimedSpeech(audio=wav_audio(frames=len(turns) * 2 * 24000), turns=turns,
                           speakers=speakers, voice_assignments={s.id: "en-GB-SoniaNeural" for s in speakers})


class DetailedSTTStub:
    def __init__(self, recognition=None, error=None):
        self.recognition = recognized_turns(SCRIPT, seconds_per_turn=2) if recognition is None else recognition
        self.error = error
        self.calls = []

    def ready(self):
        self.calls.append("ready")

    def transcribe_detailed(self, audio):
        self.calls.append(audio)
        if self.error:
            raise self.error
        return deepcopy(self.recognition)


def make_publication(*, recognition=None, error=None, invalid_manifest=False):
    exercise, answers = exercise_and_answers(SCRIPT)
    store = MemoryAudioStore((exercise, answers))
    speech = TimedSpeechStub(invalid_manifest=invalid_manifest)
    stt = DetailedSTTStub(recognition, error)
    service = AudioPublicationService(store, speech, stt)
    return service, store, speech, stt


def test_all_answer_checks_pass_before_audio_can_be_published():
    service, store, speech, stt = make_publication()
    report = service.build("exercise-1")
    assert report["status"] == "verified" and report["verification"]["delivery_allowed"]
    assert store.saves[-1]["status"] == "verified" and len(speech.calls) == 1
    assert stt.calls == ["ready", store.record["audio"]]
    assert "audio" not in report and "audio_base64" not in report and "url" not in report
    delivered = service.get_verified("exercise-1")
    assert delivered["audio"] == store.record["audio"]
    assert delivered["manifest"]["turns"][1]["start_seconds"] == 2


@pytest.mark.parametrize("defect", ["wrong-answer", "partial", "missing-words", "cancelled", "invalid-manifest"])
def test_unverified_artifacts_are_saved_blocked_and_never_delivered(defect):
    recognition = recognized_turns(SCRIPT, ["The fee is fifty pounds.", "Thank you."], seconds_per_turn=2)
    if defect != "wrong-answer":
        recognition = recognized_turns(SCRIPT, seconds_per_turn=2)
    if defect == "partial":
        recognition.complete = False
    elif defect == "missing-words":
        recognition.words = []
    error = SpeechError(502, "stt_provider_error", "Recognition cancelled") if defect == "cancelled" else None
    service, store, _, stt = make_publication(recognition=recognition, error=error,
                                              invalid_manifest=defect == "invalid-manifest")
    report = service.build("exercise-1")
    assert report["status"] == "blocked" and not report["verification"]["delivery_allowed"]
    assert store.record["status"] == "blocked"
    if defect == "invalid-manifest":
        assert stt.calls == ["ready"]
    with pytest.raises(SpeechError) as caught:
        service.get_verified("exercise-1")
    assert caught.value.status_code == 409


def test_every_question_must_pass_and_missing_key_blocks_entire_audio():
    service, store, _, _ = make_publication()
    store.source[0]["question_groups"][0]["questions"].append({"id": "question-2", "number": 2})
    report = service.build("exercise-1")
    assert report["status"] == "blocked"
    assert [check["status"] for check in report["verification"]["checks"]] == ["passed", "unverifiable"]


def test_source_change_during_generation_blocks_publication():
    service, store, _, _ = make_publication()
    store.change_during_build = True
    report = service.build("exercise-1")
    assert report["status"] == "blocked" and report["verification"]["reason"] == "source_changed"


@pytest.mark.parametrize("defect", [
    "source", "answer-key", "audio", "audio-hash", "configuration", "manifest-position",
    "manifest-source", "manifest-frame", "manifest-rate", "manifest-nan", "manifest-missing-rate",
    "manifest-voice", "missing-manifest", "missing-audio", "missing-status", "verification-type", "truthy-verified",
    "missing-checks", "failed-check", "extra-check", "current-voices", "old-pipeline", "not-verified", "source-unavailable",
])
def test_read_gate_rejects_tampered_or_incomplete_bindings(defect):
    service, store, _, _ = make_publication()
    service.build("exercise-1")
    record = store.record
    if defect == "source":
        store.source[0]["text"] += " More."
    elif defect == "answer-key":
        store.source[1]["answers"][0]["answer_key"] = "fifty"
    elif defect == "audio":
        record["audio"] = record["audio"][:-1] + b"\x01"
    elif defect == "audio-hash":
        record["audio_sha256"] = "0" * 64
    elif defect == "configuration":
        record["manifest"]["configuration"]["locale"] = "en-US"
    elif defect == "manifest-position":
        record["manifest"]["turns"][0]["position"] = 9
    elif defect == "manifest-source":
        record["manifest"]["turns"][0]["source_start_char"] += 1
    elif defect == "manifest-frame":
        record["manifest"]["turns"][0]["end_frame"] -= 1
    elif defect == "manifest-rate":
        record["manifest"]["sample_rate"] = 16000
    elif defect == "manifest-nan":
        record["manifest"]["turns"][0]["start_seconds"] = float("nan")
    elif defect == "manifest-missing-rate":
        record["manifest"].pop("sample_rate")
    elif defect == "manifest-voice":
        record["manifest"]["voice_assignments"]["speaker_1"] = "en-US-JennyNeural"
    elif defect == "missing-manifest":
        record.pop("manifest")
    elif defect == "missing-audio":
        record.pop("audio")
    elif defect == "missing-status":
        record.pop("status")
    elif defect == "verification-type":
        record["verification"] = None
    elif defect == "truthy-verified":
        record["verification"]["delivery_allowed"] = 1
    elif defect == "missing-checks":
        record["verification"].pop("checks")
    elif defect == "failed-check":
        record["verification"]["checks"][0]["status"] = "failed"
    elif defect == "extra-check":
        record["verification"]["checks"].append(deepcopy(record["verification"]["checks"][0]))
    elif defect == "current-voices":
        service.speech.settings.listening_voices = ("en-US-JennyNeural",)
    elif defect == "old-pipeline":
        record["manifest"]["configuration"]["pipeline"] = "obsolete-pipeline"
        record["config_hash"] = config_hash(record["manifest"]["configuration"])
        record["verification"]["manifest_sha256"] = config_hash(record["manifest"])
    elif defect == "not-verified":
        record["status"] = "blocked"
    else:
        store.source = None
    with pytest.raises(SpeechError) as caught:
        service.get_verified("exercise-1")
    assert caught.value.status_code == 409 and caught.value.code == "audio_not_verified"


@pytest.fixture
def publication_api():
    service, store, speech, stt = make_publication()
    bank = ApiBank()
    store.source[0]["id"] = bank.item_id
    bank.item = deepcopy(store.source[0])
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=bank,
                              agents=FakeAgents([practice_draft()]), speech=speech,
                              audio_publication=service)) as client:
        yield client, bank, service, store, stt


def test_verified_stored_audio_and_public_timings_do_not_expose_private_answers(publication_api):
    client, bank, _, store, _ = publication_api
    create = client.post(f"/api/exercises/{bank.item_id}/audio/verify", headers=AUTH)
    assert create.status_code == 200 and create.json()["status"] == "verified"
    assert "audio_base64" in create.json()  # Private authenticated authoring response.
    delivered = client.get(f"/api/exercises/{bank.item_id}/audio", headers=AUTH)
    assert delivered.status_code == 200 and delivered.content == store.record["audio"]
    assert delivered.headers["cache-control"] == "no-store"
    timings = client.get(f"/api/exercises/{bank.item_id}/audio/timings", headers=AUTH)
    assert timings.status_code == 200 and timings.headers["cache-control"] == "no-store"
    assert timings.json()["turns"][1]["start_seconds"] == 2
    assert set(timings.json()) == {"item_id", "audio_sha256", "sample_rate", "turns"}
    assert "answer_key" not in timings.text and "verification" not in timings.text and "recognized_excerpt" not in timings.text


def test_failed_stored_pipeline_returns_no_audio_in_any_delivery_path(publication_api):
    client, bank, _, store, stt = publication_api
    stt.recognition.complete = False
    report = client.post(f"/api/exercises/{bank.item_id}/audio/verify", headers=AUTH)
    assert report.status_code == 200 and report.json()["status"] == "blocked"
    assert "audio_base64" not in report.json() and "audio_url" not in report.json()
    for route in ("audio", "audio/timings"):
        response = client.get(f"/api/exercises/{bank.item_id}/{route}", headers=AUTH)
        assert response.status_code == 409 and response.headers["content-type"] == "application/json"
        assert response.json()["error"] == "audio_not_verified"
    response = client.post(f"/api/exercises/{bank.item_id}/audio", headers=AUTH)
    assert response.status_code == 409 and response.json()["error"] == "audio_verification_failed"
    assert store.record["status"] == "blocked" and "audio_base64" not in response.text


def test_public_turn_metadata_uses_allowlist_even_if_private_fields_enter_manifest(publication_api):
    client, bank, _, store, _ = publication_api
    response = client.post(f"/api/exercises/{bank.item_id}/audio/verify", headers=AUTH)
    assert response.status_code == 200 and response.json()["status"] == "verified"
    store.record["manifest"]["turns"][0].update(answer_key="fifteen", recognized_excerpt="private evidence")
    # Simulate a trusted future authoring version storing additional private
    # manifest fields; integrity still holds, delivery must project public fields.
    store.record["verification"]["manifest_sha256"] = config_hash(store.record["manifest"])
    response = client.get(f"/api/exercises/{bank.item_id}/audio/timings", headers=AUTH)
    assert response.status_code == 200
    assert "answer_key" not in response.text and "recognized_excerpt" not in response.text
    assert set(response.json()["turns"][0]) == {
        "position", "speaker_id", "start_frame", "end_frame", "start_seconds", "end_seconds",
        "source_start_char", "source_end_char",
    }


@pytest.mark.parametrize("route", ["audio", "audio/verify", "audio/timings"])
def test_stored_audio_routes_keep_global_bearer_auth(publication_api, route):
    client, bank, _, _, stt = publication_api
    method = client.get if route == "audio/timings" else client.post
    assert method(f"/api/exercises/{bank.item_id}/{route}").status_code == 401
    assert not stt.calls


@pytest.mark.parametrize("path", ["/api/listening/audio", "/api/listening/audio/verify"])
def test_raw_authoring_is_disabled_without_a_configured_bearer_token(path):
    service, _, speech, stt = make_publication()
    with TestClient(create_app(settings=Settings(), bank=ApiBank(), agents=FakeAgents([practice_draft()]),
                              speech=speech, audio_publication=service)) as client:
        response = client.post(path, json={"script": SCRIPT})
    assert response.status_code == 503 and not speech.calls and not stt.calls
