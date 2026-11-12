"""Complete-file Azure recognition, isolated from the API's worker thread.

The reference script is deliberately never passed to this adapter. A spawned
process owns the native SDK so its startup/cleanup cannot outlive the deadline.
"""

import importlib
from io import BytesIO
import json
import multiprocessing
from pathlib import Path
import re
import tempfile
import threading
import wave

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from ..core.config import Settings
from .azure_speech import MAX_AUDIO_BYTES, SpeechError


MAX_TRANSCRIPT_CHARS = 50_000
MAX_RECOGNITION_SECONDS = 720.0
MAX_RECOGNIZED_WORDS = 5_000
_SDK_MODULE = "azure.cognitiveservices.speech"


class RecognizedWord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=256, strict=True)
    start_seconds: float = Field(ge=0, allow_inf_nan=False, strict=True)
    end_seconds: float = Field(gt=0, allow_inf_nan=False, strict=True)

    @model_validator(mode="after")
    def ordered_interval(self):
        if (not self.text.strip() or self.end_seconds <= self.start_seconds or "\x00" in self.text
                or any(0xD800 <= ord(char) <= 0xDFFF for char in self.text)):
            raise ValueError("Recognized words need nonblank text and positive time intervals")
        return self


class DetailedTranscription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=MAX_TRANSCRIPT_CHARS, strict=True)
    words: list[RecognizedWord] = Field(default_factory=list, max_length=MAX_RECOGNIZED_WORDS)
    complete: StrictBool = True

    @field_validator("text")
    @classmethod
    def valid_unicode(cls, value: str) -> str:
        if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("Transcript must contain valid Unicode")
        return value


def _error(status: int, code: str, message: str) -> SpeechError:
    return SpeechError(status, code, message)


def _word_metadata(result):
    raw = getattr(result, "json", None)
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str) or len(raw) > 1_000_000:
        raise ValueError
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError
    best = data.get("NBest")
    if best is None or best == []:
        return None
    if not isinstance(best, list) or not isinstance(best[0], dict):
        raise ValueError
    words = best[0].get("Words")
    if words is None or words == []:
        return None
    if not isinstance(words, list) or len(words) > MAX_RECOGNIZED_WORDS:
        raise ValueError
    parsed = []
    for word in words:
        if not isinstance(word, dict):
            raise ValueError
        offset, duration = word.get("Offset"), word.get("Duration")
        if type(offset) is not int or type(duration) is not int or offset < 0 or duration <= 0:
            raise ValueError
        parsed.append(RecognizedWord(text=word.get("Word"), start_seconds=offset / 10_000_000,
                                     end_seconds=(offset + duration) / 10_000_000))
    return parsed


def _validate_words(words: list[RecognizedWord], duration: float) -> None:
    previous_end = 0.0
    for word in words:
        if word.start_seconds < previous_end or word.end_seconds > duration + 1e-6:
            raise ValueError("Recognition word intervals are outside the audio or out of order")
        previous_end = word.end_seconds


def _recognize_file_detailed(sdk, key: str, region: str, path: str, timeout: float,
                             duration: float) -> DetailedTranscription:
    """Run the event protocol; the production parent enforces native-call timeout."""
    done = threading.Event()
    lock = threading.Lock()
    parts = []
    failed = False
    total_chars = 0
    total_words = 0
    recognizer = None

    def recognized(event):
        nonlocal failed, total_chars, total_words
        try:
            result = event.result
            if result.reason != sdk.ResultReason.RecognizedSpeech:
                return
            text = result.text
            if not isinstance(text, str):
                raise ValueError
            words = _word_metadata(result) if text.strip() else []
            with lock:
                total_chars += len(text)
                total_words += len(words) if words is not None else 0
                if total_chars > MAX_TRANSCRIPT_CHARS or total_words > MAX_RECOGNIZED_WORDS:
                    failed = True
                    done.set()
                    return
                parts.append((getattr(result, "offset", len(parts)), text.strip(), words))
        except Exception:
            # SDK events run on native callback threads; never leak their data.
            with lock:
                failed = True
            done.set()

    def canceled(event):
        nonlocal failed
        # EndOfStream can be a normal native termination notification. The
        # session-stopped event is still required before returning the text.
        try:
            details = getattr(event, "cancellation_details", None)
            if details is None:
                details = getattr(getattr(event, "result", None), "cancellation_details", None)
            end_of_stream = getattr(sdk.CancellationReason, "EndOfStream", None)
            if details is not None and end_of_stream is not None and details.reason == end_of_stream:
                return
        except Exception:
            pass
        with lock:
            failed = True
        done.set()

    def stopped(_event):
        done.set()

    try:
        config = sdk.SpeechConfig(subscription=key, region=region)
        config.speech_recognition_language = "en-GB"
        config.output_format = sdk.OutputFormat.Detailed
        config.request_word_level_timestamps()
        audio = sdk.audio.AudioConfig(filename=path)
        recognizer = sdk.SpeechRecognizer(speech_config=config, audio_config=audio)
        recognizer.recognized.connect(recognized)
        recognizer.canceled.connect(canceled)
        recognizer.session_stopped.connect(stopped)
        recognizer.start_continuous_recognition_async().get()
        if not done.wait(timeout):
            raise _error(504, "stt_timeout", "Azure Speech recognition timed out")
        with lock:
            if failed:
                raise _error(502, "stt_provider_error", "Azure Speech could not recognize the complete audio")
            ordered = sorted(parts, key=lambda part: part[0])
            text = " ".join(text for _, text, _ in ordered if text)
            # Any phrase missing timing makes the whole word timeline
            # unavailable; never return apparently complete partial evidence.
            words = [] if any(phrase_words is None for _, _, phrase_words in ordered) else [
                word for _, _, phrase_words in ordered for word in phrase_words]
            _validate_words(words, duration)
            return DetailedTranscription(text=text, words=words)
    except SpeechError:
        raise
    except Exception:
        raise _error(502, "stt_provider_error", "Azure Speech recognition failed") from None
    finally:
        if recognizer is not None:
            try:
                recognizer.stop_continuous_recognition_async().get()
            except Exception:
                pass
            for signal, callback in ((recognizer.recognized, recognized),
                                     (recognizer.canceled, canceled),
                                     (recognizer.session_stopped, stopped)):
                try:
                    signal.disconnect(callback)
                except Exception:
                    pass


def _recognize_file(sdk, key: str, region: str, path: str, timeout: float) -> str:
    with wave.open(path, "rb") as wav:
        duration = wav.getnframes() / wav.getframerate()
    return _recognize_file_detailed(sdk, key, region, path, timeout, duration).text


def _worker(path: str, key: str, region: str, timeout: float, duration: float, connection):
    """Secrets travel over multiprocessing IPC, never command-line arguments."""
    try:
        sdk = importlib.import_module(_SDK_MODULE)
        result = _recognize_file_detailed(sdk, key, region, path, timeout, duration)
        connection.send({"ok": True, **result.model_dump()})
    except SpeechError as error:
        connection.send({"ok": False, "timeout": error.code == "stt_timeout"})
    except Exception:
        connection.send({"ok": False, "timeout": False})
    finally:
        connection.close()


class AzureSTT:
    def __init__(self, settings: Settings, sdk=None):
        self.settings = settings
        self._sdk = sdk

    def ready(self) -> None:
        if not self.settings.azure_speech_key or not re.fullmatch(r"[a-z][a-z0-9-]{1,49}", self.settings.azure_speech_region):
            raise _error(503, "stt_not_configured", "Configure Azure Speech key and region for recognition")
        if self._sdk is None:
            try:
                importlib.import_module(_SDK_MODULE)
            except (ImportError, OSError):
                raise _error(503, "stt_not_configured", "Install the listening-stt extra to enable Azure recognition") from None

    def transcribe(self, audio: bytes) -> str:
        return self.transcribe_detailed(audio).text

    def transcribe_detailed(self, audio: bytes) -> DetailedTranscription:
        self.ready()
        if not isinstance(audio, bytes) or not 0 < len(audio) <= MAX_AUDIO_BYTES:
            raise _error(422, "invalid_stt_audio", "Audio must be a bounded mono 24 kHz PCM WAV")
        try:
            with wave.open(BytesIO(audio), "rb") as wav:
                frames = wav.getnframes()
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 24000, "NONE"):
                    raise ValueError
                if not 0 < frames < 599 * 24000 or len(wav.readframes(frames)) != frames * 2:
                    raise ValueError
                duration = frames / 24000
        except (wave.Error, EOFError, ValueError, RuntimeError):
            raise _error(422, "invalid_stt_audio", "Audio must be a complete mono 24 kHz PCM WAV shorter than 599 seconds") from None
        timeout = min(MAX_RECOGNITION_SECONDS, duration + 90.0)
        with tempfile.TemporaryDirectory(prefix="ielts-stt-") as directory:
            path = Path(directory) / "audio.wav"
            path.write_bytes(audio)
            if self._sdk is not None:
                return _recognize_file_detailed(self._sdk, self.settings.azure_speech_key,
                                                self.settings.azure_speech_region, str(path), timeout, duration)
            return self._isolated_transcribe_detailed(str(path), timeout, duration)

    def _isolated_transcribe(self, path: str, timeout: float) -> str:
        return self._isolated_transcribe_detailed(path, timeout, 599.0).text

    def _isolated_transcribe_detailed(self, path: str, timeout: float,
                                     duration: float) -> DetailedTranscription:
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_worker,
                                  args=(path, self.settings.azure_speech_key,
                                        self.settings.azure_speech_region, timeout, duration, sender), daemon=True)
        started = False
        try:
            process.start()
            started = True
            sender.close()
            if not receiver.poll(timeout):
                raise _error(504, "stt_timeout", "Azure Speech recognition timed out")
            result = receiver.recv()
            if not isinstance(result, dict) or result.get("ok") is not True:
                if isinstance(result, dict) and result.get("timeout") is True:
                    raise _error(504, "stt_timeout", "Azure Speech recognition timed out")
                raise _error(502, "stt_provider_error", "Azure Speech could not recognize the complete audio")
            detailed = DetailedTranscription.model_validate({key: value for key, value in result.items() if key != "ok"})
            if not detailed.complete:
                raise _error(502, "stt_provider_error", "Azure Speech returned invalid recognition data")
            _validate_words(detailed.words, duration)
            return detailed
        except SpeechError:
            raise
        except Exception:
            raise _error(502, "stt_provider_error", "Azure Speech recognition failed") from None
        finally:
            receiver.close()
            sender.close()
            if started:
                process.join(timeout=1)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=3)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=3)
                process.close()
