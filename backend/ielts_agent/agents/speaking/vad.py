"""Audio activity measurements using the bundled Silero VAD model."""

import math
import time

import numpy as np


SAMPLE_RATE = 16000
PAUSE_SECONDS = 0.5
SETTINGS = {"threshold": 0.5, "min_silence_duration_ms": 500, "speech_pad_ms": 0}


def activity_metrics(segments, audio_seconds):
    previous_end = 0.0
    for segment in segments:
        start, end = segment["start"], segment["end"]
        if (not math.isfinite(start) or not math.isfinite(end)
                or start < previous_end or end <= start or end > audio_seconds):
            raise ValueError("Invalid VAD speech ranges")
        previous_end = end
    pauses = [{"start": round(left["end"], 3), "end": round(right["start"], 3),
               "seconds": round(right["start"] - left["end"], 3)}
              for left, right in zip(segments, segments[1:])
              if right["start"] - left["end"] >= PAUSE_SECONDS - 1e-9]
    first = segments[0]["start"] if segments else None
    last = segments[-1]["end"] if segments else None
    return {
        "status": "ok" if segments else "no_speech", "source": "silero_vad_v6",
        "settings": dict(SETTINGS), "pause_threshold_seconds": PAUSE_SECONDS,
        "audio_seconds": round(audio_seconds, 3), "speech_segments": segments,
        "speech_start_seconds": first, "speech_end_seconds": last,
        "speech_window_seconds": round(last - first, 3) if segments else None,
        "voiced_seconds": round(sum(s["end"] - s["start"] for s in segments), 3),
        "leading_non_speech_seconds": round(first, 3) if segments else None,
        "trailing_non_speech_seconds": round(audio_seconds - last, 3) if segments else None,
        "internal_pause_count": len(pauses),
        "pause_seconds": round(sum(p["seconds"] for p in pauses), 3),
        "longest_pause_seconds": max((p["seconds"] for p in pauses), default=0),
        "pauses": pauses, "words_per_minute": None,
    }


def detect_activity(samples):
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim != 1 or not samples.size or not np.isfinite(samples).all():
        raise ValueError("VAD requires finite mono audio")
    started = time.perf_counter()
    spans = get_speech_timestamps(samples, VadOptions(**SETTINGS), sampling_rate=SAMPLE_RATE)
    segments = [{"start": int(s["start"]) / SAMPLE_RATE, "end": int(s["end"]) / SAMPLE_RATE} for s in spans]
    result = activity_metrics(segments, len(samples) / SAMPLE_RATE)
    result["processing_seconds"] = round(time.perf_counter() - started, 3)
    return result
