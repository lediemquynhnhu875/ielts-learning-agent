"""Stored exercise audio: timed synthesis, private answer checks, fail-closed delivery."""

import hashlib
import math
from io import BytesIO
import wave

from ..agents.uc04.listening_turns import split_script
from ..infrastructure.azure_speech import SpeechError
from ..infrastructure.db.listening_audio import config_hash, source_hash
from .answer_checking import check_answers
from .verification import ListeningAudioVerifier

PIPELINE_VERSION = "timed-answer-stt-v1"


def _valid_manifest(audio: bytes, manifest: dict, script: str) -> bool:
    try:
        with wave.open(BytesIO(audio), "rb") as wav:
            frames = wav.getnframes()
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                return False
            if len(wav.readframes(frames)) != frames * 2:
                return False
        source_turns = split_script(script).turns
        if manifest["sample_rate"] != 24000:
            return False
        turns = manifest["turns"]
        if len(turns) != len(source_turns):
            return False
        cursor = 0
        for turn, source in zip(turns, source_turns):
            if (turn["position"] != source.position or turn["speaker_id"] != source.speaker_id
                    or turn["source_start_char"] != source.start_char or turn["source_end_char"] != source.end_char
                    or type(turn["start_frame"]) is not int or type(turn["end_frame"]) is not int
                    or type(turn["start_seconds"]) not in (int, float) or type(turn["end_seconds"]) not in (int, float)
                    or not math.isfinite(turn["start_seconds"]) or not math.isfinite(turn["end_seconds"])
                    or turn["start_frame"] != cursor or turn["end_frame"] <= cursor
                    or abs(turn["start_seconds"] - cursor / 24000) > 0.000001
                    or abs(turn["end_seconds"] - turn["end_frame"] / 24000) > 0.000001):
                return False
            cursor = turn["end_frame"]
        return cursor == frames and frames > 0
    except (KeyError, TypeError, ValueError, wave.Error, EOFError, RuntimeError):
        return False


class AudioPublicationService:
    def __init__(self, store, speech, transcriber):
        self.store, self.speech, self.transcriber = store, speech, transcriber

    def configuration(self, voices: dict | None = None) -> dict:
        return {"pipeline": PIPELINE_VERSION, "locale": "en-GB",
                "voice_pool": list(self.speech.settings.listening_voices), "overrides": voices or {}}

    def build(self, item_id: str, voices: dict[str, str] | None = None) -> dict:
        source = self.store.load_source(item_id)
        if source is None:
            raise SpeechError(404, "exercise_not_found", "Listening exercise is unavailable")
        exercise, answers = source
        expected = ListeningAudioVerifier.reference(exercise["text"])
        self.transcriber.ready()
        configuration = self.configuration(voices)
        source_binding, config_binding = source_hash(exercise, answers), config_hash(configuration)
        timed = self.speech.synthesize_timed(exercise["text"], voices)
        manifest = {"sample_rate": 24000, "configuration": configuration,
                    "voice_assignments": timed.voice_assignments,
                    "turns": [turn.model_dump() for turn in timed.turns]}
        verification = {"delivery_allowed": False, "reason": "invalid_manifest"}
        if _valid_manifest(timed.audio, manifest, exercise["text"]):
            try:
                recognition = self.transcriber.transcribe_detailed(timed.audio)
                diagnostic = ListeningAudioVerifier.compare_transcript(expected, recognition.text)
                result = check_answers(exercise["text"], exercise, answers, timed.turns, recognition)
                verification = {**result.model_dump(), "diagnostic": diagnostic.model_dump(),
                                "reason": "answers_verified" if result.delivery_allowed else "answer_checks_not_passed"}
            except SpeechError as error:
                verification = {"delivery_allowed": False, "reason": error.code}
            except ValueError:
                verification = {"delivery_allowed": False, "reason": "unverifiable_word_alignment"}
        current = self.store.load_source(item_id)
        if current is None or source_hash(*current) != source_binding:
            verification["delivery_allowed"] = False
            verification["reason"] = "source_changed"
        verification["manifest_sha256"] = config_hash(manifest)
        self.store.save(item_id, source_binding, config_binding, timed.audio, manifest, verification,
                        "verified" if verification["delivery_allowed"] else "blocked")
        return {"item_id": item_id, "status": "verified" if verification["delivery_allowed"] else "blocked",
                "verification": verification, "manifest": manifest, "source_hash": source_binding,
                "audio_sha256": hashlib.sha256(timed.audio).hexdigest()}

    def get_verified(self, item_id: str) -> dict:
        source = self.store.load_source(item_id)
        record = self.store.get(item_id) if source else None
        try:
            expected_ids = {q["id"] for group in source[0]["question_groups"] for q in group["questions"]} if source else set()
            checks = record["verification"]["checks"] if record else []
            valid = (record is not None and record["status"] == "verified" and record["verification"].get("delivery_allowed") is True
                and bool(expected_ids) and len(checks) == len(expected_ids)
                and {check["question_id"] for check in checks} == expected_ids
                and all(check["status"] == "passed" for check in checks)
                and record["source_hash"] == source_hash(*source)
                and record["audio_sha256"] == hashlib.sha256(record["audio"]).hexdigest()
                and record["config_hash"] == config_hash(record["manifest"]["configuration"])
                and record["config_hash"] == config_hash(self.configuration(record["manifest"]["configuration"]["overrides"]))
                and record["verification"]["manifest_sha256"] == config_hash(record["manifest"])
                and _valid_manifest(record["audio"], record["manifest"], source[0]["text"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            valid = False
        if not valid:
            raise SpeechError(409, "audio_not_verified", "Exercise audio is not verified for delivery")
        return record
