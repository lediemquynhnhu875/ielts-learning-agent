"""Offline alignment, round-trip verification, API and existing-audio CLI contracts."""

import base64
from copy import deepcopy
from functools import lru_cache
from itertools import product
import json
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from ielts_agent.api.main import create_app
from ielts_agent.core.config import Settings
from ielts_agent.infrastructure.azure_speech import SpeechError
from ielts_agent.listening import cli
from ielts_agent.listening.comparison import (
    MAX_COMPARISON_WORDS, MAX_TRANSCRIPT_CHARS, compare_words, words,
)
from ielts_agent.listening.verification import ListeningAudioVerifier
from .test_api import ApiBank, AUTH, TOKEN
from .test_azure_speech import wav_audio
from .test_pipeline import FakeAgents, practice_draft


class FakeSpeech:
    def __init__(self):
        self.calls = []

    def synthesize(self, script, voices=None):
        self.calls.append((script, voices))
        return wav_audio()


class FakeSTT:
    def __init__(self, transcript="Hello. Hi.", *, readiness_error=None):
        self.transcript = transcript
        self.readiness_error = readiness_error
        self.calls = []

    def ready(self):
        self.calls.append("ready")
        if self.readiness_error:
            raise self.readiness_error

    def transcribe(self, audio, /):
        # A reference or prompt argument would fail this signature.
        self.calls.append(audio)
        return self.transcript


def test_normalization_ignores_case_punctuation_and_unicode_presentation():
    result = compare_words("Ｃａｆé: I’m READY—now!", "café i'm ready, now.")
    assert result.normalized_match and result.word_error_rate == 0
    assert result.reference_word_count == result.transcript_word_count == 4
    assert not result.differences


def test_names_and_spoken_numbers_remain_literal_differences():
    result = compare_words("Linh booked room 42.", "Lynn booked room forty two.")
    assert not result.normalized_match
    assert words("42") != words("forty two")
    assert any("linh" in change.expected for change in result.differences)
    assert any("42" in change.expected for change in result.differences)


@pytest.mark.parametrize("reference, transcript, counts, kind", [
    ("red green blue", "red blue", (0, 1, 0), "deletion"),
    ("red blue", "red green blue", (0, 0, 1), "insertion"),
    ("red green blue", "red yellow purple", (2, 0, 0), "substitution"),
], ids=["deleted-word", "inserted-word", "adjacent-substitutions"])
def test_alignment_groups_adjacent_changes_with_token_ranges(reference, transcript, counts, kind):
    result = compare_words(reference, transcript)
    assert (result.substitutions, result.deletions, result.insertions) == counts
    assert len(result.differences) == 1
    change = result.differences[0]
    assert change.kind == kind
    assert change.reference_start == change.transcript_start == 1
    assert change.expected == " ".join(words(reference)[change.reference_start:change.reference_end])
    assert change.recognized == " ".join(words(transcript)[change.transcript_start:change.transcript_end])


def test_wer_is_not_clamped_when_insertions_outnumber_reference():
    result = compare_words("go", "please go now soon")
    assert result.word_error_rate == 3
    assert (result.substitutions, result.deletions, result.insertions) == (0, 0, 3)


def test_empty_transcript_is_all_deletions_at_comparison_layer():
    result = compare_words("red green blue", "")
    assert result.deletions == 3 and result.word_error_rate == 1
    assert len(result.differences) == 1 and result.differences[0].recognized == ""


def test_alignment_distance_is_minimal_for_small_repeated_word_sequences():
    @lru_cache(maxsize=None)
    def distance(left, right):
        if not left:
            return len(right)
        if not right:
            return len(left)
        return min(distance(left[1:], right) + 1, distance(left, right[1:]) + 1,
                   distance(left[1:], right[1:]) + (left[0] != right[0]))

    sequences = [tuple(seq) for size in range(4) for seq in product(("a", "b"), repeat=size)]
    for expected in sequences[1:]:
        for actual in sequences:
            result = compare_words(" ".join(expected), " ".join(actual))
            errors = result.substitutions + result.deletions + result.insertions
            assert errors == distance(expected, actual), (expected, actual)
            assert result.normalized_match == (expected == actual)
            assert result.word_error_rate == round(errors / len(expected), 6)
            previous_reference = previous_transcript = 0
            for change in result.differences:
                assert previous_reference <= change.reference_start <= change.reference_end <= len(expected)
                assert previous_transcript <= change.transcript_start <= change.transcript_end <= len(actual)
                assert change.expected == " ".join(expected[change.reference_start:change.reference_end])
                assert change.recognized == " ".join(actual[change.transcript_start:change.transcript_end])
                previous_reference, previous_transcript = change.reference_end, change.transcript_end


@pytest.mark.parametrize("reference, transcript", [
    ("...", "word"), ("x " * (MAX_COMPARISON_WORDS + 1), "word"),
    ("word", "x " * (MAX_COMPARISON_WORDS + 1)),
    ("x" * (MAX_TRANSCRIPT_CHARS + 1), "word"),
    ("word", "x" * (MAX_TRANSCRIPT_CHARS + 1)),
], ids=["no-reference-words", "reference-words", "transcript-words", "reference-chars", "transcript-chars"])
def test_comparison_rejects_unbounded_or_empty_reference(reference, transcript):
    with pytest.raises(ValueError):
        compare_words(reference, transcript)


def test_max_reference_word_boundary_can_be_compared_to_missing_speech():
    result = compare_words("x " * MAX_COMPARISON_WORDS, "")
    assert result.deletions == MAX_COMPARISON_WORDS


def test_pipeline_synthesizes_and_transcribes_exactly_once_without_reference_hints():
    speech, stt = FakeSpeech(), FakeSTT()
    script = "Man: Hello. Woman: Hi."
    voices = {"speaker_1": "en-GB-RyanNeural"}
    result = ListeningAudioVerifier(speech, stt).generate(script, voices)
    assert speech.calls == [(script, voices)]
    assert stt.calls == ["ready", wav_audio()]
    assert result.verification.expected_text == "Hello.\nHi."
    assert result.verification.transcript == "Hello. Hi."
    assert result.verification.comparison.normalized_match
    assert base64.b64decode(result.audio_base64) == wav_audio()
    assert result.audio_media_type == "audio/wav"


def test_pipeline_returns_mismatch_without_correcting_script_or_audio():
    speech, stt = FakeSpeech(), FakeSTT("Goodbye. Hi.")
    script = "Man: Hello. Woman: Hi."
    result = ListeningAudioVerifier(speech, stt).generate(script)
    assert result.verification.expected_text == "Hello.\nHi."
    assert result.verification.transcript == "Goodbye. Hi."
    assert result.verification.comparison.substitutions == 1
    assert not result.verification.comparison.normalized_match
    assert "TTS or STT" in result.verification.review_note
    assert speech.calls == [(script, None)]
    assert base64.b64decode(result.audio_base64) == wav_audio()


def test_stt_readiness_fails_before_paid_tts():
    speech = FakeSpeech()
    stt = FakeSTT(readiness_error=SpeechError(503, "stt_not_configured", "STT unavailable"))
    with pytest.raises(SpeechError) as caught:
        ListeningAudioVerifier(speech, stt).generate("Hello.")
    assert caught.value.status_code == 503 and not speech.calls
    assert stt.calls == ["ready"]


@pytest.mark.parametrize("script", ["Man:", "...", "x " * (MAX_COMPARISON_WORDS + 1)],
                         ids=["empty-turn", "no-words", "word-limit"])
def test_reference_errors_fail_before_stt_or_tts(script):
    speech, stt = FakeSpeech(), FakeSTT()
    with pytest.raises(SpeechError) as caught:
        ListeningAudioVerifier(speech, stt).generate(script)
    assert caught.value.status_code == 422 and not speech.calls and not stt.calls


@pytest.mark.parametrize("transcript", [None, "", " \n", "...", "word\x00", "word\ud800",
    "x" * (MAX_TRANSCRIPT_CHARS + 1), "x " * (MAX_COMPARISON_WORDS + 1)],
    ids=["non-text", "empty", "blank", "no-words", "nul", "surrogate", "too-long", "too-many-words"])
def test_invalid_stt_transcripts_return_safe_failure(transcript):
    speech, stt = FakeSpeech(), FakeSTT(transcript)
    with pytest.raises(SpeechError) as caught:
        ListeningAudioVerifier(speech, stt).generate("Hello.")
    assert caught.value.status_code == 502 and caught.value.code == "invalid_stt_transcript"
    assert len(speech.calls) == 1 and stt.calls == ["ready", wav_audio()]


def test_existing_audio_verification_never_synthesizes_again():
    speech, stt = FakeSpeech(), FakeSTT("Hello.")
    result = ListeningAudioVerifier(speech, stt).verify_audio("Speaker 1: Hello.", wav_audio())
    assert result.comparison.normalized_match and not speech.calls
    assert stt.calls == ["ready", wav_audio()]


@pytest.fixture
def verification_api():
    from .test_audio_publication import PreviewPublication

    class CountingBank(ApiBank):
        def __init__(self):
            super().__init__()
            self.reads = 0

        def get_item(self, item_id):
            self.reads += 1
            return super().get_item(item_id)

    bank = CountingBank()
    bank.item.update(skill="listening", text="Man: Hello. Woman: Hi.")
    speech, stt = FakeSpeech(), FakeSTT()
    verifier = ListeningAudioVerifier(speech, stt)
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=bank,
                              agents=FakeAgents([practice_draft()]), speech=speech,
                              audio_verifier=verifier, audio_publication=PreviewPublication())) as client:
        yield client, bank, speech, stt


def test_raw_preview_and_stored_publication_return_audio_without_source_changes(verification_api):
    client, bank, speech, stt = verification_api
    original = deepcopy(bank.item)
    raw = client.post("/api/listening/audio/verify", json={"script": original["text"]}, headers=AUTH)
    saved = client.post(f"/api/exercises/{bank.item_id}/audio/verify", headers=AUTH)
    assert raw.status_code == saved.status_code == 200
    assert raw.json()["audio_base64"] == saved.json()["audio_base64"]
    assert saved.json()["status"] == "verified" and saved.json()["verification"]["delivery_allowed"]
    assert raw.headers["cache-control"] == saved.headers["cache-control"] == "no-store"
    assert base64.b64decode(raw.json()["audio_base64"]) == wav_audio()
    assert raw.json()["verification"]["comparison"]["normalized_match"]
    assert bank.item == original and not bank.saved
    # Raw authoring keeps its diagnostic contract. Stored authoring uses a
    # separately injected publication pipeline, tested against real gates elsewhere.
    assert len(speech.calls) == 1 and stt.calls.count(wav_audio()) == 1
    prior_stt = list(stt.calls)
    legacy = client.post("/api/listening/audio", json={"script": original["text"]}, headers=AUTH)
    assert legacy.status_code == 200 and legacy.content == wav_audio()
    assert legacy.headers["content-type"] == "audio/wav" and stt.calls == prior_stt


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_verify_routes_authenticate_before_database_or_speech(verification_api, headers):
    client, bank, speech, stt = verification_api
    assert client.post("/api/listening/audio/verify", json={"script": "Hello."}, headers=headers).status_code == 401
    assert client.post(f"/api/exercises/{bank.item_id}/audio/verify", headers=headers).status_code == 401
    assert bank.reads == 0 and not speech.calls and not stt.calls


def test_item_verification_validates_item_and_options_before_speech(verification_api):
    client, bank, speech, stt = verification_api
    assert client.post("/api/exercises/invalid/audio/verify", headers=AUTH).status_code == 422
    assert bank.reads == 0
    assert client.post(f"/api/exercises/{uuid4()}/audio/verify", headers=AUTH).status_code == 404
    assert client.post(f"/api/exercises/{bank.item_id}/audio/verify", json={"extra": True}, headers=AUTH).status_code == 422
    bank.item["skill"] = "reading"
    assert client.post(f"/api/exercises/{bank.item_id}/audio/verify", headers=AUTH).status_code == 422
    assert not speech.calls and not stt.calls


@pytest.mark.parametrize("payload", [{}, {"script": 4}, {"script": " "}, {"script": "Hi", "extra": True}],
                         ids=["missing", "non-string", "blank", "extra"])
def test_raw_verify_request_validation(verification_api, payload):
    client, _, speech, stt = verification_api
    assert client.post("/api/listening/audio/verify", json=payload, headers=AUTH).status_code == 422
    assert not speech.calls and not stt.calls


def test_verify_api_sanitizes_surrogates_and_stt_service_errors(verification_api):
    client, _, speech, stt = verification_api
    response = client.post("/api/listening/audio/verify", content=b'{"script":"\\ud800"}',
                           headers={**AUTH, "Content-Type": "application/json"})
    assert response.status_code == 422 and not speech.calls
    stt.readiness_error = SpeechError(503, "stt_not_configured", "Install the STT dependency")
    response = client.post("/api/listening/audio/verify", json={"script": "Hello."}, headers=AUTH)
    assert response.status_code == 503 and response.json()["error"] == "stt_not_configured"
    assert response.headers["cache-control"] == "no-store" and not speech.calls


def test_cli_reuses_existing_wav_and_saves_report(tmp_path, monkeypatch, capsys):
    audio = tmp_path / "existing.wav"
    script = tmp_path / "script.txt"
    report = tmp_path / "reports" / "comparison.json"
    audio.write_bytes(wav_audio())
    script.write_text("Narrator: Hello.", encoding="utf-8")
    stt = FakeSTT("Hello!")
    monkeypatch.setattr(cli, "AzureSTT", lambda settings: stt)
    monkeypatch.setattr(cli.Settings, "from_env", lambda: Settings())
    monkeypatch.setattr(cli.AzureSpeech, "synthesize", lambda *_: pytest.fail("CLI must not synthesize"))
    monkeypatch.setattr(sys, "argv", ["cli", "--audio", str(audio), "--script", str(script), "--output", str(report)])
    assert cli.main() == 0
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["comparison"]["normalized_match"] and body["expected_text"] == "Hello."
    assert stt.calls == ["ready", wav_audio()]
    assert json.loads(capsys.readouterr().out)["report_path"] == str(report)


def test_cli_missing_input_returns_clean_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli", "--audio", str(tmp_path / "missing.wav"),
                                     "--script", str(tmp_path / "missing.txt")])
    assert cli.main() == 1
    assert json.loads(capsys.readouterr().out)["error"] == "verification_file_error"


@pytest.mark.parametrize("output_kind", ["audio", "script"])
def test_cli_output_cannot_overwrite_reference_or_audio(tmp_path, monkeypatch, capsys, output_kind):
    audio = tmp_path / "existing.wav"
    script = tmp_path / "script.txt"
    audio.write_bytes(wav_audio())
    script.write_text("Narrator: Hello.", encoding="utf-8")
    output = audio if output_kind == "audio" else script
    monkeypatch.setattr(cli.Settings, "from_env", lambda: pytest.fail("Reject output before initializing providers"))
    monkeypatch.setattr(sys, "argv", ["cli", "--audio", str(audio), "--script", str(script), "--output", str(output)])
    assert cli.main() == 1
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_verification_output"
    assert audio.read_bytes() == wav_audio() and script.read_text(encoding="utf-8") == "Narrator: Hello."
