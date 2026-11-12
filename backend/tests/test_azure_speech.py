"""Azure synthesis contracts tested offline with generated PCM and MockTransport."""

from copy import deepcopy
from io import BytesIO
import struct
from uuid import uuid4
import wave
from xml.etree import ElementTree

from fastapi.testclient import TestClient
import httpx
import pytest

from ielts_agent.api.main import create_app
from ielts_agent.core.config import Settings
from ielts_agent.infrastructure import azure_speech as module
from ielts_agent.infrastructure.azure_speech import AzureSpeech, SpeechError
from .test_api import ApiBank, AUTH, TOKEN
from .test_pipeline import FakeAgents, practice_draft


def wav_audio(*, channels=1, rate=24000, frames=24):
    buffer = BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\x00\x00" * channels * frames)
    return buffer.getvalue()


def configured(**updates):
    return Settings(azure_speech_key="offline-speech-test-key", azure_speech_region="eastus", **updates)


def provider(*, settings=None, status=200, body=None, exception=None):
    calls = []

    def respond(request):
        calls.append(request)
        if exception:
            raise exception
        return httpx.Response(status, content=wav_audio() if body is None else body)

    return AzureSpeech(settings or configured(), transport=httpx.MockTransport(respond)), calls


def voice_elements(request):
    return list(ElementTree.fromstring(request.content))


def test_ssml_preserves_turn_order_escapes_text_and_reuses_voice():
    service, calls = provider()
    script = 'Man: Hello & <audio src="https://example.org"/>. Woman: Hi. Man: Again.'
    assert service.synthesize(script) == wav_audio()
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"
    assert request.headers["Ocp-Apim-Subscription-Key"] == "offline-speech-test-key"
    assert request.headers["X-Microsoft-OutputFormat"] == "riff-24khz-16bit-mono-pcm"
    elements = voice_elements(request)
    assert [e.attrib["name"] for e in elements] == ["en-GB-SoniaNeural", "en-GB-RyanNeural", "en-GB-SoniaNeural"]
    assert [e.text for e in elements] == ['Hello & <audio src="https://example.org"/>.', "Hi.", "Again."]
    assert all(len(element) == 0 for element in elements)


def test_explicit_voice_override_and_pool_rotation():
    service, calls = provider()
    service.synthesize("Man: One. Woman: Two. Caller: Three.", {"speaker_2": "en-US-JennyNeural"})
    assert [e.attrib["name"] for e in voice_elements(calls[0])] == ["en-GB-SoniaNeural", "en-US-JennyNeural", "en-GB-SoniaNeural"]


@pytest.mark.parametrize("script, voices", [
    ("", {}), ("Man:", {}), ("hello\x01", {}), ("hello\ud800", {}),
    ("hello", {"speaker_9": "en-US-JennyNeural"}),
    ("hello", {"speaker_1": 'en-US-X\"/><audio src="https://example.org"/>'}),
    ("x" * (module.MAX_SCRIPT_CHARS + 1), {}),
    (" ".join("Man: hello." for _ in range(module.MAX_VOICE_ELEMENTS + 1)), {}),
], ids=["blank", "empty-turn", "xml-control", "surrogate", "unknown-speaker", "voice-injection", "script-limit", "turn-limit"])
def test_invalid_synthesis_inputs_fail_before_network(script, voices):
    service, calls = provider()
    with pytest.raises(SpeechError) as caught:
        service.synthesize(script, voices)
    assert caught.value.status_code == 422 and not calls


def test_escaped_ssml_near_source_limit_remains_valid():
    service, calls = provider()
    # Exercise escaping with close-to-limit source length and all 50 turns.
    script = " ".join("Man: " + "&" * 232 for _ in range(50))
    assert len(script) <= module.MAX_SCRIPT_CHARS
    assert service.synthesize(script) == wav_audio()
    assert len(calls) == 1 and len(calls[0].content) <= 64_000
    assert all(element.text == "&" * 232 for element in voice_elements(calls[0]))


@pytest.mark.parametrize("settings", [Settings(), configured(listening_voices=()),
    configured(listening_voices=('bad"voice',)),
    Settings(azure_speech_key="offline-key", azure_speech_region="eastus.evil.example"),
    Settings(azure_speech_key="offline-key", azure_speech_region="eastus/../../")],
    ids=["missing", "empty-pool", "invalid-pool", "host-injection", "path-injection"])
def test_unconfigured_or_unsafe_settings_never_call_provider(settings):
    service, calls = provider(settings=settings)
    with pytest.raises(SpeechError) as caught:
        service.synthesize("Hello.")
    assert caught.value.status_code == 503 and not calls


@pytest.mark.parametrize("status, expected", [(401, 502), (500, 502), (429, 503), (302, 502)])
def test_provider_errors_sanitized_and_never_retried(status, expected):
    service, calls = provider(status=status, body=b"private provider body offline-speech-test-key")
    with pytest.raises(SpeechError) as caught:
        service.synthesize("Hello.")
    assert caught.value.status_code == expected
    assert "private" not in str(caught.value) and "offline-speech-test-key" not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("error, status", [(httpx.ReadTimeout("private timeout"), 504),
    (httpx.ConnectError("private connection"), 502)])
def test_transport_failures_safe(error, status):
    service, calls = provider(exception=error)
    with pytest.raises(SpeechError) as caught:
        service.synthesize("Hello.")
    assert caught.value.status_code == status and "private" not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"", b"not WAV", wav_audio(channels=2), wav_audio(rate=16000),
    wav_audio(frames=0), wav_audio()[:-3],
    b"RIFF" + struct.pack("<I", 12) + b"WAVEJUNK" + struct.pack("<I", 0xffffffff)],
    ids=["empty", "non-wav", "stereo", "wrong-rate", "no-frames", "truncated", "malformed-chunk"])
def test_invalid_audio_is_rejected(body):
    service, _ = provider(body=body)
    with pytest.raises(SpeechError) as caught:
        service.synthesize("Hello.")
    assert caught.value.code == "invalid_speech_audio"


def test_audio_stream_cap(monkeypatch):
    monkeypatch.setattr(module, "MAX_AUDIO_BYTES", 50)
    service, _ = provider(body=wav_audio())
    with pytest.raises(SpeechError, match="oversized"):
        service.synthesize("Hello.")


def test_elapsed_deadline_rejects_delayed_audio(monkeypatch):
    times = iter([0, module.SYNTHESIS_TIMEOUT + 1])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(times))
    service, _ = provider()
    with pytest.raises(SpeechError) as caught:
        service.synthesize("Hello.")
    assert caught.value.status_code == 504 and caught.value.code == "speech_timeout"


@pytest.fixture
def speech_api():
    from .test_audio_publication import PreviewPublication

    bank = ApiBank()
    bank.item.update(skill="listening", text="Man: Hello. Woman: Hi.")
    service, calls = provider()
    with TestClient(create_app(settings=configured(api_token=TOKEN), bank=bank,
                              agents=FakeAgents([practice_draft()]), speech=service,
                              audio_publication=PreviewPublication())) as client:
        yield client, bank, calls


def test_audio_apis_return_wav_without_mutating_exercise(speech_api):
    client, bank, calls = speech_api
    original = deepcopy(bank.item)
    raw = client.post("/api/listening/audio", json={"script": bank.item["text"]}, headers=AUTH)
    stored = client.post(f"/api/exercises/{bank.item_id}/audio", headers=AUTH)
    assert raw.status_code == stored.status_code == 200
    assert raw.content == stored.content == wav_audio()
    assert raw.headers["content-type"] == "audio/wav"
    assert raw.headers["cache-control"] == "no-store"
    assert "listening.wav" in raw.headers["content-disposition"]
    # The stored path now uses the publication gate, rather than raw preview TTS.
    assert bank.item == original and not bank.saved and len(calls) == 1
    assert client.get(f"/api/exercises/{bank.item_id}", headers=AUTH).json() == original
    split = client.post("/api/listening/turns", json={"script": original["text"]}, headers=AUTH)
    assert split.status_code == 200 and len(split.json()["turns"]) == 2


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_audio_routes_require_existing_bearer(speech_api, headers):
    client, bank, calls = speech_api
    assert client.post("/api/listening/audio", json={"script": "Hello."}, headers=headers).status_code == 401
    assert client.post(f"/api/exercises/{bank.item_id}/audio", headers=headers).status_code == 401
    assert not calls


@pytest.mark.parametrize("payload", [{}, {"script": 12}, {"script": " "}, {"script": "Hi", "unknown": True},
    {"script": "Hi", "voices": {"speaker_1": 12}}, {"script": "Man:"}],
    ids=["missing", "nonstring", "blank", "extra", "invalid-voice-type", "empty-turn"])
def test_audio_request_validation(speech_api, payload):
    client, _, calls = speech_api
    assert client.post("/api/listening/audio", json=payload, headers=AUTH).status_code == 422
    assert not calls


def test_audio_surrogate_json_returns_422(speech_api):
    client, _, calls = speech_api
    response = client.post("/api/listening/audio", content=b'{"script":"\\ud800"}',
                           headers={**AUTH, "Content-Type": "application/json"})
    assert response.status_code == 422 and not calls


def test_item_audio_validates_item_and_body(speech_api):
    client, bank, calls = speech_api
    assert client.post("/api/exercises/invalid/audio", headers=AUTH).status_code == 422
    assert client.post(f"/api/exercises/{uuid4()}/audio", headers=AUTH).status_code == 404
    assert client.post(f"/api/exercises/{bank.item_id}/audio", json={"extra": True}, headers=AUTH).status_code == 422
    bank.item["skill"] = "reading"
    assert client.post(f"/api/exercises/{bank.item_id}/audio", headers=AUTH).status_code == 422
    assert not calls


def test_config_reads_shared_azure_settings_and_voice_pool(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "offline-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", " westus ")
    monkeypatch.setenv("LISTENING_VOICES", " en-US-JennyNeural, en-US-GuyNeural ")
    settings = Settings.from_env()
    assert settings.azure_speech_key == "offline-key" and settings.azure_speech_region == "westus"
    assert settings.listening_voices == ("en-US-JennyNeural", "en-US-GuyNeural")
    assert "offline-key" not in repr(settings)
