"""
Chạy thử Whisper cho phần Agent Speaking (Groq V3; local V3 Turbo).

Cách dùng:
    python test_whisper.py audio.wav                 # gọi Groq API
    python test_whisper.py audio.wav --local         # chạy trên máy bằng faster-whisper
    python test_whisper.py audio.wav --keep-fillers  # thêm prompt giữ từ đệm (um, uh)

Cài đặt:
    pip install groq                # cho cách 1
    pip install faster-whisper      # cho cách 2
    Đặt biến môi trường GROQ_API_KEY (lấy key miễn phí tại console.groq.com)
"""

import argparse
import json
import os
import re

# Word hints only: whole example sentences can bias the decoded language/content.
# Whisper prompts are context/style hints, not reliable instruction following.
FILLER_PROMPT = "um, uh, hmm, ừm, ờ, à"


def transcription_prompt(keep_fillers, vocabulary=""):
    """Spelling hints, never a reference answer or a post-transcription rewrite."""
    parts = []
    if vocabulary.strip():
        parts.append(vocabulary.strip()[:400])
    if keep_fillers:
        parts.append(FILLER_PROMPT)
    return "; ".join(parts) or None


def groq_stt_model():
    model = os.environ.get("SPEAKING_STT_MODEL") or "whisper-large-v3"
    if model not in {"whisper-large-v3", "whisper-large-v3-turbo"}:
        raise ValueError("SPEAKING_STT_MODEL must be whisper-large-v3 or whisper-large-v3-turbo")
    return model

FILLERS = {"um", "umm", "uh", "uhm", "er", "erm", "hmm", "ah", "like"}
PAUSE_THRESHOLD = 0.5  # giây; khoảng lặng giữa hai từ dài hơn mức này tính là ngừng


def transcribe_groq(path, keep_fillers, client=None, vocabulary=""):
    from groq import Groq

    if client is None:
        client = Groq()  # đọc GROQ_API_KEY từ biến môi trường
    with open(path, "rb") as f:
        result = client.audio.transcriptions.create(
            file=f,
            model=groq_stt_model(),
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
            # Omit language: let the multilingual transcription endpoint detect
            # the spoken language. Never use audio.translations here.
            temperature=0.0,
            prompt=transcription_prompt(keep_fillers, vocabulary),
        )
    data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    words = [
        {"word": w["word"].strip(), "start": w["start"], "end": w["end"]}
        for w in data.get("words") or []
    ]
    return data.get("text", "").strip(), words


def transcribe_local(path, keep_fillers, model=None, word_timestamps=True, vocabulary=""):
    from faster_whisper import WhisperModel

    # Có GPU NVIDIA: device="cuda", compute_type="float16"
    if model is None:
        model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        path,
        language=None,
        task="transcribe",
        multilingual=True,  # detect language for each segment, including switches
        word_timestamps=word_timestamps,
        temperature=0.0,
        initial_prompt=transcription_prompt(keep_fillers, vocabulary),
        vad_filter=False,  # tắt để không cắt mất các khoảng ngừng cần đo
    )
    text_parts, words = [], []
    for seg in segments:
        text_parts.append(seg.text.strip())
        for w in seg.words or []:
            words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
    return " ".join(text_parts), words


def fluency_metrics(words):
    if not words:
        return {}
    clean = [re.sub(r"[^\w']", "", w["word"].lower()) for w in words]
    duration = words[-1]["end"] - words[0]["start"]

    pauses = []
    for prev, cur in zip(words, words[1:]):
        gap = cur["start"] - prev["end"]
        if gap >= PAUSE_THRESHOLD:
            pauses.append({"after": prev["word"], "at": round(prev["end"], 2), "length": round(gap, 2)})

    repeats = [
        clean[i] for i in range(1, len(clean)) if clean[i] and clean[i] == clean[i - 1]
    ]

    return {
        "so_tu": len(words),
        "thoi_luong_giay": round(duration, 1),
        "toc_do_tu_moi_phut": round(len(words) / duration * 60, 1) if duration else 0,
        "so_lan_ngung": len(pauses),
        "tong_thoi_gian_ngung": round(sum(p["length"] for p in pauses), 1),
        "ngung_dai_nhat": max((p["length"] for p in pauses), default=0),
        "so_tu_dem": sum(1 for w in clean if w in FILLERS),
        "lap_tu": repeats,
        "cac_lan_ngung": pauses,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--local", action="store_true", help="chạy faster-whisper trên máy")
    ap.add_argument("--keep-fillers", action="store_true", help="thêm prompt giữ từ đệm")
    ap.add_argument("--vocabulary", default="", help="gợi ý cách viết tên riêng, không nhập câu trả lời mẫu")
    args = ap.parse_args()

    if not args.local and not os.environ.get("GROQ_API_KEY"):
        raise SystemExit("Chưa đặt GROQ_API_KEY. Lấy key tại console.groq.com hoặc dùng --local.")

    fn = transcribe_local if args.local else transcribe_groq
    text, words = fn(args.audio, args.keep_fillers, vocabulary=args.vocabulary)

    print("=== TRANSCRIPT ===")
    print(text)
    print("\n=== CHỈ SỐ TRÔI CHẢY ===")
    print(json.dumps(fluency_metrics(words), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
