"""Timed synthesis measures WAV frames rather than estimating source timings."""

from io import BytesIO
import struct
import wave
from xml.etree import ElementTree

import httpx
import pytest

from ielts_agent.agents.uc04.listening_turns import split_script
from ielts_agent.core.config import Settings
from ielts_agent.infrastructure import azure_speech as module
from ielts_agent.infrastructure.azure_speech import AzureSpeech, SpeechError


def wav_audio(frames=240, sample=100):
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(struct.pack("<h", sample) * frames)
    return output.getvalue()


def service_for(responses, *, settings=None, on_request=None):
    calls = []

    def respond(request):
        calls.append(request)
        if on_request is not None:
            on_request(len(calls))
        result = responses[len(calls) - 1]
        if isinstance(result, int):
            return httpx.Response(result, content=b"private provider details")
        return httpx.Response(200, content=result)

    settings = settings or Settings(azure_speech_key="offline-timed-key", azure_speech_region="eastus")
    return AzureSpeech(settings, transport=httpx.MockTransport(respond)), calls


def test_timed_synthesis_concatenates_pcm_and_measures_exact_frame_windows():
    frame_counts = [240, 720, 480]
    samples = [100, -50, 200]
    service, calls = service_for([wav_audio(frames, sample) for frames, sample in zip(frame_counts, samples)])
    script = "Man: Hello & welcome.\nWoman: Good morning.\nMan: Thank you."
    result = service.synthesize_timed(script, {"speaker_2": "en-US-JennyNeural"})
    assert len(calls) == 3
    assert [str(request.url) for request in calls] == [
        "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"] * 3
    voice_elements = [list(ElementTree.fromstring(request.content)) for request in calls]
    assert all(len(elements) == 1 for elements in voice_elements)
    assert [elements[0].attrib["name"] for elements in voice_elements] == [
        "en-GB-SoniaNeural", "en-US-JennyNeural", "en-GB-SoniaNeural"]
    assert [elements[0].text for elements in voice_elements] == ["Hello & welcome.", "Good morning.", "Thank you."]
    assert result.voice_assignments == {"speaker_1": "en-GB-SoniaNeural", "speaker_2": "en-US-JennyNeural"}
    assert [speaker.label for speaker in result.speakers] == ["Man", "Woman"]
    assert [(turn.start_frame, turn.end_frame) for turn in result.turns] == [(0, 240), (240, 960), (960, 1440)]
    assert [(turn.start_seconds, turn.end_seconds) for turn in result.turns] == [(0, .01), (.01, .04), (.04, .06)]
    parsed = split_script(script)
    for timing, turn in zip(result.turns, parsed.turns):
        assert timing.position == turn.position
        assert timing.speaker_id == turn.speaker_id
        assert script[timing.source_start_char:timing.source_end_char] == turn.text
    with wave.open(BytesIO(result.audio), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24000)
        assert wav.getnframes() == sum(frame_counts)
        assert wav.readframes(wav.getnframes() + 1) == b"".join(
            struct.pack("<h", sample) * frames for frames, sample in zip(frame_counts, samples))
    assert len(result.audio) == 44 + sum(frame_counts) * 2


def test_monologue_keeps_one_voice_and_has_one_measured_window():
    service, calls = service_for([wav_audio(1200)])
    result = service.synthesize_timed("An unlabelled short lecture.")
    assert len(calls) == len(result.turns) == len(result.speakers) == 1
    assert result.speakers[0].label == "Narrator"
    assert result.turns[0].start_frame == 0 and result.turns[0].end_frame == 1200


@pytest.mark.parametrize("script, voices", [
    ("Man: Hello. Woman: \x01bad.", {}),
    ("Man: Hello. Woman:", {}),
    ("Man: Hello. Woman: Goodbye.", {"speaker_3": "en-US-JennyNeural"}),
    ("Man: Hello. Woman: Goodbye.", {"speaker_2": "bad-voice"}),
    ("x" * (module.MAX_SCRIPT_CHARS + 1), {}),
    (" ".join("Man: Hi." for _ in range(module.MAX_VOICE_ELEMENTS + 1)), {}),
], ids=["invalid-later-text", "empty-later-turn", "unknown-speaker", "bad-later-voice", "script-limit", "turn-limit"])
def test_all_turn_inputs_are_validated_before_first_paid_call(script, voices):
    service, calls = service_for([])
    with pytest.raises(SpeechError) as caught:
        service.synthesize_timed(script, voices)
    assert caught.value.status_code == 422 and not calls


def test_timed_synthesis_checks_provider_configuration_before_paid_calls():
    service, calls = service_for([], settings=Settings())
    with pytest.raises(SpeechError) as caught:
        service.synthesize_timed("Man: Hello. Woman: Goodbye.")
    assert caught.value.code == "speech_not_configured" and not calls


@pytest.mark.parametrize("second_response, expected_code", [(500, "speech_provider_error"), (429, "speech_busy"),
    (b"broken WAV", "invalid_speech_audio")], ids=["provider-failure", "rate-limit", "invalid-later-wav"])
def test_later_failure_does_not_return_partial_audio_or_retry(second_response, expected_code):
    service, calls = service_for([wav_audio(), second_response, wav_audio()])
    with pytest.raises(SpeechError) as caught:
        service.synthesize_timed("Man: First. Woman: Second. Man: Third.")
    assert len(calls) == 2
    assert caught.value.code == expected_code
    assert "private" not in str(caught.value)


def test_combined_size_limit_counts_one_final_header(monkeypatch):
    monkeypatch.setattr(module, "MAX_AUDIO_BYTES", 100)
    service, calls = service_for([wav_audio(15), wav_audio(15)])
    with pytest.raises(SpeechError, match="size limit"):
        service.synthesize_timed("Man: Hello. Woman: Goodbye.")
    assert len(calls) == 2


def test_combined_duration_limit_rejects_individually_valid_turns(monkeypatch):
    monkeypatch.setattr(module, "MAX_AUDIO_SECONDS", 2.0)
    service, calls = service_for([wav_audio(36000), wav_audio(36000)])
    with pytest.raises(SpeechError, match="duration limit"):
        service.synthesize_timed("Man: Hello. Woman: Goodbye.")
    assert len(calls) == 2


def test_whole_generation_budget_prevents_next_paid_request(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    original_pcm = AzureSpeech._pcm

    def advance_after_first_audio(audio):
        result = original_pcm(audio)
        clock[0] = module.TIMED_SYNTHESIS_TIMEOUT + 1
        return result

    monkeypatch.setattr(AzureSpeech, "_pcm", staticmethod(advance_after_first_audio))
    service, calls = service_for([wav_audio(), wav_audio()])
    with pytest.raises(SpeechError) as caught:
        service.synthesize_timed("Man: Hello. Woman: Goodbye.")
    assert caught.value.status_code == 504 and len(calls) == 1
