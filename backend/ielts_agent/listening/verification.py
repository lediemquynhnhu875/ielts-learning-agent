"""Recognize a synthesized WAV once and report lexical differences without correction."""

import base64
from typing import Protocol

from pydantic import BaseModel

from ..agents.uc04.listening_turns import split_script
from ..infrastructure.azure_speech import AzureSpeech, SpeechError, SynthesizeScriptRequest
from .comparison import MAX_COMPARISON_WORDS, MAX_TRANSCRIPT_CHARS, TextComparison, compare_words, words


class Transcriber(Protocol):
    def ready(self) -> None: ...
    def transcribe(self, audio: bytes) -> str: ...


class AudioVerification(BaseModel):
    stt_provider: str = "azure"
    locale: str = "en-GB"
    expected_text: str
    transcript: str
    comparison: TextComparison
    review_note: str = "Differences can come from TTS or STT. Review the audio; no automatic correction was applied."


class VerifiedAudio(BaseModel):
    audio_base64: str
    audio_media_type: str = "audio/wav"
    verification: AudioVerification


class ListeningAudioVerifier:
    def __init__(self, speech: AzureSpeech, transcriber: Transcriber):
        self.speech = speech
        self.transcriber = transcriber

    @staticmethod
    def reference(script: str) -> str:
        try:
            script = SynthesizeScriptRequest(script=script).script
            expected = "\n".join(turn.text for turn in split_script(script).turns)
        except ValueError:
            raise SpeechError(422, "invalid_speech_request", "Script is invalid or contains an empty speaker turn") from None
        token_count = len(words(expected))
        if not 0 < token_count <= MAX_COMPARISON_WORDS:
            raise SpeechError(422, "invalid_comparison_reference", "Spoken reference must contain 1 to 2500 words")
        return expected

    def _verify(self, expected: str, audio: bytes) -> AudioVerification:
        # Only audio crosses the STT boundary: no reference text or vocabulary hints.
        transcript = self.transcriber.transcribe(audio)
        return self.compare_transcript(expected, transcript)

    @staticmethod
    def compare_transcript(expected: str, transcript: str) -> AudioVerification:
        if (not isinstance(transcript, str) or not transcript.strip() or len(transcript) > MAX_TRANSCRIPT_CHARS
                or any(0xD800 <= ord(c) <= 0xDFFF or c == "\x00" for c in transcript)):
            raise SpeechError(502, "invalid_stt_transcript", "STT returned an empty or invalid transcript")
        if not words(transcript):
            raise SpeechError(502, "invalid_stt_transcript", "STT returned no recognizable words")
        try:
            comparison = compare_words(expected, transcript)
        except ValueError:
            raise SpeechError(502, "invalid_stt_transcript", "STT transcript exceeds comparison limits") from None
        return AudioVerification(expected_text=expected, transcript=transcript, comparison=comparison)

    def verify_audio(self, script: str, audio: bytes) -> AudioVerification:
        expected = self.reference(script)
        self.transcriber.ready()
        return self._verify(expected, audio)

    def generate(self, script: str, voices: dict[str, str] | None = None) -> VerifiedAudio:
        expected = self.reference(script)
        self.transcriber.ready()
        audio = self.speech.synthesize(script, voices)
        verification = self._verify(expected, audio)
        return VerifiedAudio(audio_base64=base64.b64encode(audio).decode("ascii"), verification=verification)
