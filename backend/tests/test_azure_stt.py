"""Offline recognition protocol, bounded worker and WAV validation checks."""

from io import BytesIO
from pathlib import Path
import struct
import json
from types import SimpleNamespace
import wave

import pytest

from ielts_agent.core.config import Settings
from ielts_agent.infrastructure import azure_stt as module
from ielts_agent.infrastructure.azure_speech import SpeechError
from ielts_agent.infrastructure.azure_stt import AzureSTT, DetailedTranscription


def wav_audio(*, channels=1, rate=24000, frames=24):
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\0\0" * channels * frames)
    return buffer.getvalue()


def settings(**changes):
    return Settings(azure_speech_key="offline-recognition-key", azure_speech_region="eastus", **changes)


class Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def disconnect(self, callback):
        self.callbacks.remove(callback)

    def emit(self, event=None):
        for callback in list(self.callbacks):
            callback(event)


class Future:
    def __init__(self, callback):
        self.callback = callback

    def get(self):
        return self.callback()


class FakeSDK:
    ResultReason = SimpleNamespace(RecognizedSpeech="speech", NoMatch="no-match")
    CancellationReason = SimpleNamespace(Error="error", EndOfStream="eof")
    OutputFormat = SimpleNamespace(Detailed="detailed")

    def __init__(self, events=()):
        self.events = events
        self.configs = []
        self.files = []
        self.recognizers = []
        self.timestamp_requests = 0
        self.audio = SimpleNamespace(AudioConfig=self.audio_config)

    def SpeechConfig(self, **kwargs):
        config = SimpleNamespace(**kwargs)
        def request_timestamps():
            self.timestamp_requests += 1
        config.request_word_level_timestamps = request_timestamps
        self.configs.append(config)
        return config

    def audio_config(self, *, filename):
        assert Path(filename).read_bytes().startswith(b"RIFF")
        self.files.append(Path(filename))
        return SimpleNamespace(filename=filename)

    def SpeechRecognizer(self, *, speech_config, audio_config):
        recognizer = SimpleNamespace(recognized=Signal(), canceled=Signal(), session_stopped=Signal(), stop_calls=0)

        def start():
            for event in self.events:
                if event[0] == "text":
                    recognizer.recognized.emit(SimpleNamespace(result=SimpleNamespace(
                        text=event[1], reason="speech", offset=event[2], json=event[3] if len(event) > 3 else None)))
                elif event[0] == "no-match":
                    recognizer.recognized.emit(SimpleNamespace(result=SimpleNamespace(reason="no-match")))
                elif event[0] == "cancel":
                    details = SimpleNamespace(reason=event[1], code="none" if event[1] == "eof" else "failure",
                                              error_details="PRIVATE SDK ERROR offline-recognition-key")
                    recognizer.canceled.emit(SimpleNamespace(cancellation_details=details))
                elif event[0] == "cancel-result":
                    details = SimpleNamespace(reason=event[1], code="none" if event[1] == "eof" else "failure")
                    recognizer.canceled.emit(SimpleNamespace(result=SimpleNamespace(cancellation_details=details)))
                elif event[0] == "cancel-missing-details":
                    recognizer.canceled.emit(SimpleNamespace())
                elif event[0] == "stop":
                    recognizer.session_stopped.emit()
                elif event[0] == "exception":
                    raise RuntimeError("PRIVATE SDK ERROR offline-recognition-key")

        def stop():
            recognizer.stop_calls += 1

        recognizer.start_continuous_recognition_async = lambda: Future(start)
        recognizer.stop_continuous_recognition_async = lambda: Future(stop)
        self.recognizers.append(recognizer)
        return recognizer


def test_full_file_recognition_collects_phrases_in_audio_order_and_cleans_tempfile():
    sdk = FakeSDK([("text", "Second phrase.", 100), ("text", "First phrase.", 0), ("stop",)])
    assert AzureSTT(settings(), sdk=sdk).transcribe(wav_audio()) == "First phrase. Second phrase."
    assert sdk.configs[0].speech_recognition_language == "en-GB"
    assert sdk.configs[0].output_format == "detailed"
    assert sdk.timestamp_requests == 1
    assert set(vars(sdk.configs[0])) == {"subscription", "region", "speech_recognition_language", "output_format", "request_word_level_timestamps"}
    assert not sdk.files[0].exists()
    recognizer = sdk.recognizers[0]
    assert recognizer.stop_calls == 1
    assert not recognizer.recognized.callbacks and not recognizer.canceled.callbacks
    assert not recognizer.session_stopped.callbacks


def test_normal_end_of_stream_still_requires_session_stop():
    sdk = FakeSDK([("text", "Complete.", 0), ("cancel", "eof"), ("stop",)])
    assert AzureSTT(settings(), sdk=sdk).transcribe(wav_audio()) == "Complete."


def test_end_of_stream_can_use_result_cancellation_details():
    sdk = FakeSDK([("text", "Complete.", 0), ("cancel-result", "eof"), ("stop",)])
    assert AzureSTT(settings(), sdk=sdk).transcribe(wav_audio()) == "Complete."


def timed_json(words):
    return json.dumps({"NBest": [{"Words": words}]})


def test_detailed_result_preserves_absolute_word_times_and_lexical_words():
    words = [{"Word": "five", "Offset": 1_000_000, "Duration": 2_000_000},
             {"Word": "thirty", "Offset": 5_000_000, "Duration": 2_000_000}]
    sdk = FakeSDK([("text", "5:30.", 0, timed_json(words)), ("cancel", "eof"), ("stop",)])
    result = AzureSTT(settings(), sdk=sdk).transcribe_detailed(wav_audio(frames=24000))
    assert result.complete is True and result.text == "5:30."
    assert [word.model_dump() for word in result.words] == [
        {"text": "five", "start_seconds": 0.1, "end_seconds": 0.3},
        {"text": "thirty", "start_seconds": 0.5, "end_seconds": 0.7}]
    assert len(sdk.recognizers) == sdk.timestamp_requests == 1


def test_one_phrase_missing_word_times_discards_partial_timing_evidence():
    sdk = FakeSDK([("text", "Hello.", 0, timed_json([
        {"Word": "hello", "Offset": 100_000, "Duration": 1_000_000}])),
        ("text", "Again.", 2_000_000), ("stop",)])
    result = AzureSTT(settings(), sdk=sdk).transcribe_detailed(wav_audio(frames=24000))
    assert result.complete and result.text == "Hello. Again." and result.words == []


def test_multiple_phrase_word_offsets_are_absolute_without_adding_phrase_offset():
    sdk = FakeSDK([
        ("text", "First.", 10_000_000, timed_json([{"Word": "first", "Offset": 10_000_000, "Duration": 2_000_000}])),
        ("text", "Second.", 30_000_000, timed_json([{"Word": "second", "Offset": 30_000_000, "Duration": 2_000_000}])),
        ("stop",)])
    result = AzureSTT(settings(), sdk=sdk).transcribe_detailed(wav_audio(frames=4 * 24000))
    assert result.text == "First. Second."
    assert [(word.start_seconds, word.end_seconds) for word in result.words] == [(1.0, 1.2), (3.0, 3.2)]


@pytest.mark.parametrize("raw", [None, "", "{}", '{"NBest":[]}', '{"NBest":[{"Words":[]}]}'],
                         ids=["missing", "empty-json", "no-nbest", "empty-nbest", "empty-words"])
def test_missing_word_metadata_is_unavailable_without_invented_times(raw):
    sdk = FakeSDK([("text", "Hello.", 0, raw), ("stop",)])
    result = AzureSTT(settings(), sdk=sdk).transcribe_detailed(wav_audio())
    assert result.text == "Hello." and result.complete and result.words == []


@pytest.mark.parametrize("words", [
    [{"Word": "hello", "Offset": -1, "Duration": 2}],
    [{"Word": "hello", "Offset": 0, "Duration": 0}],
    [{"Word": "hello", "Offset": float("nan"), "Duration": 2}],
    [{"Word": "hello", "Offset": True, "Duration": 2}],
    [{"Word": "hello", "Offset": "0", "Duration": 2}],
    [{"Word": "hello", "Offset": 10_000_000, "Duration": 2_000_000}],
    [{"Word": "first", "Offset": 3_000_000, "Duration": 2_000_000},
     {"Word": "second", "Offset": 2_000_000, "Duration": 2_000_000}],
    [{"Word": "first", "Offset": 1_000_000, "Duration": 3_000_000},
     {"Word": "second", "Offset": 3_000_000, "Duration": 2_000_000}],
    [{"Word": "", "Offset": 0, "Duration": 2}],
], ids=["negative", "zero-duration", "nan", "bool", "string", "beyond-audio", "out-of-order", "overlap", "empty-word"])
def test_invalid_provided_word_metadata_fails_safely(words):
    sdk = FakeSDK([("text", "Hello.", 0, timed_json(words)), ("stop",)])
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings(), sdk=sdk).transcribe_detailed(wav_audio(frames=24000))
    assert caught.value.code == "stt_provider_error" and sdk.recognizers[0].stop_calls == 1


def test_transcribe_keeps_legacy_text_interface_and_calls_stt_once(monkeypatch):
    service = AzureSTT(settings(), sdk=FakeSDK())
    calls = []
    def detailed(audio):
        calls.append(audio)
        return DetailedTranscription(text="Only once.")
    monkeypatch.setattr(service, "transcribe_detailed", detailed)
    assert service.transcribe(b"audio") == "Only once." and calls == [b"audio"]


def test_completed_no_match_returns_empty_transcript_for_comparison():
    sdk = FakeSDK([("no-match",), ("stop",)])
    assert AzureSTT(settings(), sdk=sdk).transcribe(wav_audio()) == ""


@pytest.mark.parametrize("events", [
    [("text", "Partial phrase.", 0), ("cancel", "error")],
    [("exception",)],
    [("text", 123, 0), ("stop",)],
    [("text", "Partial phrase.", 0), ("cancel-result", "error")],
    [("text", "Partial phrase.", 0), ("cancel-missing-details",)],
], ids=["partial-cancel", "sdk-exception", "invalid-text", "result-error", "missing-details"])
def test_recognition_errors_never_return_partial_text_or_provider_details(events):
    sdk = FakeSDK(events)
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings(), sdk=sdk).transcribe(wav_audio())
    assert caught.value.status_code == 502 and caught.value.code == "stt_provider_error"
    assert "PRIVATE" not in str(caught.value) and "offline-recognition-key" not in str(caught.value)
    assert sdk.recognizers[0].stop_calls == 1 and not sdk.files[0].exists()


def test_event_timeout_stops_recognition_and_deletes_tempfile(monkeypatch):
    monkeypatch.setattr(module, "MAX_RECOGNITION_SECONDS", 0.001)
    sdk = FakeSDK([("text", "Partial.", 0), ("cancel", "eof")])
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings(), sdk=sdk).transcribe(wav_audio())
    assert caught.value.status_code == 504 and caught.value.code == "stt_timeout"
    assert sdk.recognizers[0].stop_calls == 1 and not sdk.files[0].exists()


def test_transcript_size_is_bounded(monkeypatch):
    monkeypatch.setattr(module, "MAX_TRANSCRIPT_CHARS", 8)
    sdk = FakeSDK([("text", "too much content", 0), ("stop",)])
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings(), sdk=sdk).transcribe(wav_audio())
    assert caught.value.code == "stt_provider_error"


def test_word_metadata_size_is_bounded(monkeypatch):
    monkeypatch.setattr(module, "MAX_RECOGNIZED_WORDS", 1)
    words = [{"Word": "first", "Offset": 0, "Duration": 1_000_000},
             {"Word": "second", "Offset": 2_000_000, "Duration": 1_000_000}]
    sdk = FakeSDK([("text", "First second.", 0, timed_json(words)), ("stop",)])
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings(), sdk=sdk).transcribe_detailed(wav_audio(frames=24000))
    assert caught.value.code == "stt_provider_error"


@pytest.mark.parametrize("audio", [b"", b"not WAV", wav_audio(channels=2), wav_audio(rate=16000),
    wav_audio(frames=0), wav_audio()[:-3],
    b"RIFF" + struct.pack("<I", 12) + b"WAVEJUNK" + struct.pack("<I", 0xffffffff)],
    ids=["empty", "non-wav", "stereo", "wrong-rate", "empty-frames", "truncated", "bad-chunk"])
def test_invalid_audio_never_starts_sdk(audio):
    sdk = FakeSDK()
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings(), sdk=sdk).transcribe(audio)
    assert caught.value.status_code == 422 and caught.value.code == "invalid_stt_audio"
    assert not sdk.recognizers


def test_oversized_audio_never_starts_sdk(monkeypatch):
    monkeypatch.setattr(module, "MAX_AUDIO_BYTES", 50)
    sdk = FakeSDK()
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings(), sdk=sdk).transcribe(wav_audio())
    assert caught.value.code == "invalid_stt_audio" and not sdk.recognizers


@pytest.mark.parametrize("configuration", [Settings(), Settings(azure_speech_key="offline", azure_speech_region="evil.example.org")])
def test_ready_rejects_missing_or_invalid_credentials(configuration):
    with pytest.raises(SpeechError) as caught:
        AzureSTT(configuration, sdk=FakeSDK()).ready()
    assert caught.value.status_code == 503 and caught.value.code == "stt_not_configured"


def test_ready_missing_optional_sdk_is_safe(monkeypatch):
    def missing(_name):
        raise ImportError("PRIVATE module detail")
    monkeypatch.setattr(module.importlib, "import_module", missing)
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings()).ready()
    assert caught.value.code == "stt_not_configured" and "PRIVATE" not in str(caught.value)


class FakeProcess:
    def __init__(self):
        self.started = False
        self.alive = False
        self.terminated = False
        self.killed = False
        self.closed = False

    def start(self):
        self.started = True
        self.alive = True

    def join(self, timeout):
        pass

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.terminated = True
        self.alive = False

    def kill(self):
        self.killed = True
        self.alive = False

    def close(self):
        self.closed = True


def fake_context(monkeypatch, result, *, responsive=True):
    process = FakeProcess()
    receiver = SimpleNamespace(poll=lambda timeout: responsive, recv=lambda: result, close=lambda: None)
    sender = SimpleNamespace(close=lambda: None)
    context = SimpleNamespace(Pipe=lambda duplex: (receiver, sender), Process=lambda **kwargs: process)
    monkeypatch.setattr(module.multiprocessing, "get_context", lambda method: context)
    return process


def test_isolated_worker_returns_only_valid_bounded_transcript(monkeypatch):
    process = fake_context(monkeypatch, {"ok": True, "text": "A complete transcript."})
    assert AzureSTT(settings())._isolated_transcribe("audio.wav", 10) == "A complete transcript."
    assert process.started and process.terminated and process.closed


def test_isolated_worker_preserves_word_metadata(monkeypatch):
    process = fake_context(monkeypatch, {"ok": True, "text": "Hello.", "complete": True,
        "words": [{"text": "hello", "start_seconds": 0.2, "end_seconds": 0.5}]})
    result = AzureSTT(settings())._isolated_transcribe_detailed("audio.wav", 10, 1.0)
    assert result.text == "Hello." and result.complete and result.words[0].end_seconds == 0.5
    assert process.closed


@pytest.mark.parametrize("result", [
    {"ok": True, "text": "Hello.", "complete": False},
    {"ok": True, "text": "Hello.", "words": [{"text": "hello", "start_seconds": 0.2, "end_seconds": 2.0}]},
    {"ok": True, "text": "Hello.", "words": [{"text": "hello", "start_seconds": False, "end_seconds": 0.5}]},
    {"ok": True, "text": "\ud800"},
], ids=["incomplete", "invalid-time", "bool-time", "invalid-unicode"])
def test_isolated_worker_rejects_incomplete_or_invalid_detailed_results(monkeypatch, result):
    fake_context(monkeypatch, result)
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings())._isolated_transcribe_detailed("audio.wav", 10, 1.0)
    assert caught.value.code == "stt_provider_error"


def test_hung_native_worker_is_terminated_at_deadline(monkeypatch):
    process = fake_context(monkeypatch, None, responsive=False)
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings())._isolated_transcribe("audio.wav", 0.001)
    assert caught.value.code == "stt_timeout" and process.terminated and process.closed


@pytest.mark.parametrize("result", [{"ok": False, "timeout": False}, {"ok": True, "text": None}, [], {"ok": False, "timeout": True}],
                         ids=["provider", "invalid-text", "malformed", "timeout"])
def test_worker_failure_messages_are_sanitized(monkeypatch, result):
    process = fake_context(monkeypatch, result)
    with pytest.raises(SpeechError) as caught:
        AzureSTT(settings())._isolated_transcribe("audio.wav", 10)
    assert caught.value.code in {"stt_provider_error", "stt_timeout"} and process.closed
