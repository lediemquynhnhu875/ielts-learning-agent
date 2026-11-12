"""Azure REST synthesis with optional measured turn windows, without retries."""

from dataclasses import dataclass
from io import BytesIO
import re
import time
import wave
from xml.sax.saxutils import escape

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..agents.uc04.listening_turns import Speaker, ScriptTurns, SplitScriptRequest, split_script
from ..core.config import Settings


MAX_AUDIO_BYTES = 29_000_000
MAX_SCRIPT_CHARS = 12_000
MAX_VOICE_ELEMENTS = 50
SYNTHESIS_TIMEOUT = 120.0
TIMED_SYNTHESIS_TIMEOUT = 300.0
MAX_AUDIO_SECONDS = 599.0
SAMPLE_RATE = 24000
_VOICE = re.compile(r"[a-z]{2,3}-[A-Z]{2}-[A-Za-z][A-Za-z0-9-]{0,90}Neural")


class AudioOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voices: dict[str, str] = Field(default_factory=dict, max_length=50)


class SynthesizeScriptRequest(SplitScriptRequest, AudioOptions):
    script: str = Field(min_length=1, max_length=MAX_SCRIPT_CHARS, strict=True)


class SpeechTurnTiming(BaseModel):
    position: int
    speaker_id: str
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    source_start_char: int
    source_end_char: int


@dataclass(frozen=True)
class TimedSpeech:
    audio: bytes
    turns: list[SpeechTurnTiming]
    speakers: list[Speaker]
    voice_assignments: dict[str, str]


class SpeechError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _invalid(message: str):
    raise SpeechError(422, "invalid_speech_request", message)


def _voice_valid(voice: str) -> bool:
    return isinstance(voice, str) and _VOICE.fullmatch(voice) is not None


class AzureSpeech:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def _prepare(self, script: str, voices: dict[str, str] | None) -> tuple[ScriptTurns, dict[str, str]]:
        if len(script) > MAX_SCRIPT_CHARS:
            _invalid(f"Audio scripts are limited to {MAX_SCRIPT_CHARS} characters")
        if any(not (c in "\t\n\r" or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF) for c in script):
            _invalid("Script contains characters unsupported by XML")
        try:
            parsed = split_script(script)
        except ValueError:
            _invalid("Script is invalid or contains an empty speaker turn")
        voices = voices or {}
        if set(voices) - {speaker.id for speaker in parsed.speakers}:
            _invalid("Voice overrides contain an unknown speaker ID")
        if any(not _voice_valid(voice) for voice in voices.values()):
            _invalid("Voice overrides must be Azure Neural voice shortnames")
        if len(parsed.turns) > MAX_VOICE_ELEMENTS:
            _invalid(f"Audio synthesis supports up to {MAX_VOICE_ELEMENTS} turns")
        settings = self.settings
        if (not settings.azure_speech_key or not re.fullmatch(r"[a-z][a-z0-9-]{1,49}", settings.azure_speech_region)
                or not settings.listening_voices or any(not _voice_valid(v) for v in settings.listening_voices)):
            raise SpeechError(503, "speech_not_configured", "Configure Azure Speech key, region and Listening voices")
        assigned = {speaker.id: voices.get(speaker.id, settings.listening_voices[index % len(settings.listening_voices)])
                    for index, speaker in enumerate(parsed.speakers)}
        return parsed, assigned

    @staticmethod
    def _render(turns, assigned: dict[str, str]) -> bytes:
        parts = ['<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-GB">']
        for turn in turns:
            parts.append(f'<voice name="{assigned[turn.speaker_id]}">{escape(turn.text)}</voice>')
        ssml = ("".join(parts) + "</speak>").encode("utf-8")
        if len(ssml) > 64_000:
            _invalid("Escaped SSML exceeds the synthesis request limit")
        return ssml

    def _request(self, client: httpx.Client, ssml: bytes, started: float, budget: float) -> bytes:
        headers = {"Ocp-Apim-Subscription-Key": self.settings.azure_speech_key,
                   "Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
                   "User-Agent": "ielts-learning-agent"}
        try:
            remaining = budget - (time.monotonic() - started)
            if remaining <= 0:
                raise SpeechError(504, "speech_timeout", "Azure Speech synthesis timed out")
            with client.stream("POST", f"https://{self.settings.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1",
                               headers=headers, content=ssml, timeout=min(SYNTHESIS_TIMEOUT, remaining)) as response:
                if response.status_code == 429:
                    raise SpeechError(503, "speech_busy", "Azure Speech is busy; try again later")
                if response.status_code != 200:
                    raise SpeechError(502, "speech_provider_error", "Azure Speech could not synthesize this script")
                output = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if time.monotonic() - started > budget:
                        raise SpeechError(504, "speech_timeout", "Azure Speech synthesis timed out")
                    if len(output) + len(chunk) > MAX_AUDIO_BYTES:
                        raise SpeechError(502, "invalid_speech_audio", "Azure Speech returned oversized audio")
                    output.extend(chunk)
        except httpx.TimeoutException:
            raise SpeechError(504, "speech_timeout", "Azure Speech synthesis timed out") from None
        except httpx.HTTPError:
            raise SpeechError(502, "speech_provider_error", "Azure Speech could not be reached") from None
        return bytes(output)

    @staticmethod
    def _pcm(audio: bytes) -> tuple[int, bytes]:
        try:
            with wave.open(BytesIO(audio), "rb") as wav:
                frames = wav.getnframes()
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
                    raise ValueError
                pcm = wav.readframes(frames)
                if not 0 < frames < MAX_AUDIO_SECONDS * SAMPLE_RATE or len(pcm) != frames * 2:
                    raise ValueError
        except (wave.Error, EOFError, ValueError, RuntimeError):
            raise SpeechError(502, "invalid_speech_audio", "Azure Speech returned invalid or incomplete WAV audio") from None
        return frames, pcm

    def synthesize(self, script: str, voices: dict[str, str] | None = None) -> bytes:
        """Preserve the authoring preview: one multi-voice Azure request."""
        parsed, assigned = self._prepare(script, voices)
        ssml = self._render(parsed.turns, assigned)
        started = time.monotonic()
        with httpx.Client(transport=self.transport, timeout=SYNTHESIS_TIMEOUT, follow_redirects=False) as client:
            audio = self._request(client, ssml, started, SYNTHESIS_TIMEOUT)
        self._pcm(audio)
        return audio

    def synthesize_timed(self, script: str, voices: dict[str, str] | None = None) -> TimedSpeech:
        """Measure independent turn windows from separately synthesized PCM frames.

        No timing is inferred from source length or recognized text. All request
        payloads are validated before the first billable provider call.
        """
        parsed, assigned = self._prepare(script, voices)
        requests = [self._render([turn], assigned) for turn in parsed.turns]
        merged = bytearray()
        timings = []
        total_frames = 0
        started = time.monotonic()
        with httpx.Client(transport=self.transport, timeout=SYNTHESIS_TIMEOUT, follow_redirects=False) as client:
            for turn, ssml in zip(parsed.turns, requests):
                audio = self._request(client, ssml, started, TIMED_SYNTHESIS_TIMEOUT)
                frames, pcm = self._pcm(audio)
                if len(merged) + len(pcm) + 44 > MAX_AUDIO_BYTES:
                    raise SpeechError(502, "invalid_speech_audio", "Combined Listening audio exceeds the size limit")
                end_frame = total_frames + frames
                if end_frame >= MAX_AUDIO_SECONDS * SAMPLE_RATE:
                    raise SpeechError(502, "invalid_speech_audio", "Combined Listening audio exceeds the duration limit")
                timings.append(SpeechTurnTiming(position=turn.position, speaker_id=turn.speaker_id,
                    start_frame=total_frames, end_frame=end_frame,
                    start_seconds=total_frames / SAMPLE_RATE, end_seconds=end_frame / SAMPLE_RATE,
                    source_start_char=turn.start_char, source_end_char=turn.end_char))
                merged.extend(pcm)
                total_frames = end_frame
        output = BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(merged)
        return TimedSpeech(audio=output.getvalue(), turns=timings, speakers=parsed.speakers,
                           voice_assignments=assigned)
