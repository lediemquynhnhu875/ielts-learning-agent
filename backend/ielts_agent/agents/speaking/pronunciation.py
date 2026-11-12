"""Opt-in acoustic feedback. Native Azure scores are never IELTS bands."""

import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import wave

import numpy as np


def capabilities():
    try:
        sdk = importlib.util.find_spec("azure.cognitiveservices.speech") is not None
    except ModuleNotFoundError:
        sdk = False
    return {"provider": "azure", "configured": sdk and bool(os.getenv("AZURE_SPEECH_KEY")) and bool(os.getenv("AZURE_SPEECH_REGION")),
            "sdk_installed": sdk, "locale": "en-US", "mode": "unscripted",
            "ielts_band_available": False, "requires_audio_consent": True}


def score(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100 else None


def parse_segments(payloads, seconds):
    """Offsets are Azure ticks relative to this clip, not Groq token offsets."""
    segments = []
    names = {"AccuracyScore": "accuracy", "FluencyScore": "fluency", "ProsodyScore": "prosody", "PronScore": "pronunciation"}
    for data in payloads:
        best = (data.get("NBest") or [{}])[0]
        native = best.get("PronunciationAssessment", {})
        words = []
        for word in best.get("Words", []):
            start = word.get("Offset", 0) / 10_000_000
            end = start + word.get("Duration", 0) / 10_000_000
            if not (0 <= start < end <= seconds + .1):
                continue
            pa = word.get("PronunciationAssessment", {})
            words.append({"word": word.get("Word", ""), "start_s": round(start, 4), "end_s": round(end, 4),
                          "accuracy": score(pa.get("AccuracyScore")), "error_type": pa.get("ErrorType", "None"),
                          "phonemes": [{"phoneme": p.get("Phoneme"), "accuracy": score(p.get("PronunciationAssessment", {}).get("AccuracyScore"))}
                                       for p in word.get("Phonemes", [])],
                          "prosody_feedback": pa.get("Feedback", {})})
        if words and any(score(native.get(k)) is not None for k in names):
            segments.append({"recognized_text": best.get("Display", ""), "scores": {v: score(native.get(k)) for k, v in names.items()}, "words": words})
    # A transparent descriptive aggregate, not Azure's full-session scoring formula.
    means = {}
    for name in names.values():
        available = [(s["scores"][name], len(s["words"])) for s in segments if s["scores"][name] is not None]
        means[name] = round(sum(v * w for v, w in available) / sum(w for _, w in available), 2) if available else None
    return {"segments": segments, "scores": means, "aggregation": "word_count_weighted_segment_mean"}


def recognize_file(path, seconds):
    import azure.cognitiveservices.speech as sdk

    config = sdk.SpeechConfig(subscription=os.environ["AZURE_SPEECH_KEY"], region=os.environ["AZURE_SPEECH_REGION"])
    config.speech_recognition_language = "en-US"
    recognizer = sdk.SpeechRecognizer(speech_config=config, audio_config=sdk.audio.AudioConfig(filename=str(path)))
    pronunciation = sdk.PronunciationAssessmentConfig(reference_text="", grading_system=sdk.PronunciationAssessmentGradingSystem.HundredMark,
                                                       granularity=sdk.PronunciationAssessmentGranularity.Phoneme, enable_miscue=False)
    pronunciation.enable_prosody_assessment()
    pronunciation.apply_to(recognizer)
    done, payloads, errors = threading.Event(), [], []

    def recognized(event):
        if event.result.reason == sdk.ResultReason.RecognizedSpeech:
            try:
                payloads.append(json.loads(event.result.json))
            except (ValueError, TypeError):
                errors.append("invalid_response")

    def canceled(event):
        if event.result.cancellation_details.reason == sdk.CancellationReason.Error:
            errors.append("provider_error")
        done.set()

    recognizer.recognized.connect(recognized)
    recognizer.canceled.connect(canceled)
    recognizer.session_stopped.connect(lambda _: done.set())
    try:
        recognizer.start_continuous_recognition_async().get()
        if not done.wait(min(240, seconds + 60)):
            errors.append("timeout")
    finally:
        recognizer.stop_continuous_recognition_async().get()
    if errors:
        raise RuntimeError("Incomplete pronunciation assessment")
    return payloads


def assess_audio(samples, consent=False, recognize=None):
    result = {"provider": "azure", "status": "not_requested", "locale": "en-US", "mode": "unscripted",
              "score_scale": "0–100", "ielts_band": None, "calibration_status": "not_calibrated",
              "audio_consent": bool(consent), "segments": [], "scores": {},
              "limitations": ["Feedback luyện phát âm tiếng Anh, chưa hiệu chỉnh thành band IELTS.",
                              "Tên riêng và từ tiếng Việt có thể bị nhận sai; hãy nghe lại trước khi kết luận lỗi.",
                              "Transcript Azure chỉ phục vụ phân tích âm thanh, không thay transcript Groq."]}
    if not consent:
        return result
    if not capabilities()["configured"] and recognize is None:
        return {**result, "status": "not_configured"}
    seconds = len(samples) / 16000
    try:
        with tempfile.TemporaryDirectory(prefix="speaking-pronunciation-") as folder:
            path = Path(folder) / "audio.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
            parsed = parse_segments((recognize or recognize_file)(path, seconds), seconds)
        return {**result, **parsed, "status": "assessed" if parsed["segments"] else "no_speech"}
    except Exception:
        # Preserve STT even when the optional service fails; never expose provider/key details.
        return {**result, "status": "unavailable"}
