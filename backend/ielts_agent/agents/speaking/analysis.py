"""Validate STT output before deriving timing-based Speaking measurements."""

from collections import Counter
import math
import re

from ielts_agent.agents.speaking.test_whisper import FILLERS, fluency_metrics


def tokens(text):
    # Unicode letters: Vietnamese must not disappear or split at every accent.
    return re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?|\d+", text.lower())


def repeated_sentences(text):
    sentences = [" ".join(tokens(s)) for s in re.split(r"[.!?]+", text)]
    return [{"text": sentence, "count": count}
            for sentence, count in Counter(sentences).items()
            if len(sentence.split()) >= 4 and count >= 3]


def disfluency_candidates(text):
    clean = tokens(text)
    phrases, repairs = [], []
    index = 0
    while index < len(clean):
        for width in range(4, 1, -1):
            phrase = clean[index:index + width]
            count = 1
            while len(phrase) == width and clean[index + count * width:index + (count + 1) * width] == phrase:
                count += 1
            if count >= 2:
                phrases.append({"text": " ".join(phrase), "count": count,
                                "token_start": index, "token_end": index + count * width})
                index += count * width
                break
        else:
            index += 1
    for index, token in enumerate(clean):
        if token in {"sorry", "actually", "rather", "no"} or clean[index:index + 2] == ["i", "mean"]:
            repairs.append({"type": "explicit_marker", "marker": "i mean" if token == "i" else token, "token_start": index})
        if token in {"than", "because", "when", "which"}:
            previous = next((j for j in range(index - 2, max(-1, index - 7), -1) if clean[j] == token), None)
            if previous is not None:
                repairs.append({"type": "restarted_connector", "marker": token,
                                "token_start": previous, "token_end": index + 1})
    return {"repeated_phrases": phrases, "repair_candidates": repairs}


def analyze(transcript, words, audio_seconds, audio_activity=None):
    issues = []

    def issue(code, message, indices=None, severity="error"):
        issues.append({"code": code, "severity": severity, "message": message, "word_indices": indices or []})

    transcript_tokens = tokens(transcript)
    if not transcript_tokens:
        issue("empty_transcript", "Không nhận được lời nói. Hãy nghe lại hoặc thu một bản mới.")
    repeated = repeated_sentences(transcript)
    if repeated:
        issue("repeated_content", "Transcript có câu lặp từ 3 lần trở lên. Cần nghe lại để xác nhận nội dung.")
    short_repeats = [s for s, count in Counter(" ".join(tokens(s)) for s in re.split(r"[.!?]+", transcript)).items()
                     if 2 <= len(s.split()) <= 3 and count >= 3]
    if short_repeats:
        issue("repeated_short_sentences", "Transcript có câu ngắn lặp từ 3 lần. Cần nghe lại để xác nhận.", severity="warning")
    if not words:
        issue("missing_timestamps", "Không có timestamps từng từ; chưa thể tính tốc độ nói hoặc khoảng dừng.")

    invalid, outside, reversed_order, zero_duration, long_duration, non_speech_overlap = [], [], [], [], [], []
    previous_start = -1.0
    for index, word in enumerate(words):
        start, end = word.get("start"), word.get("end")
        if (not isinstance(word.get("word"), str)
                or isinstance(start, bool) or isinstance(end, bool)
                or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or not math.isfinite(start) or not math.isfinite(end)
                or end < start):
            invalid.append(index)
            continue
        if start < 0 or end > audio_seconds + 0.1:
            outside.append(index)
        if start < previous_start - 0.02:
            reversed_order.append(index)
        if tokens(word["word"]) and end == start:
            zero_duration.append(index)
        if end - start >= 1.5:
            long_duration.append(index)
        if audio_activity and audio_activity.get("status") == "ok" and end > start:
            voiced = sum(max(0, min(end, s["end"]) - max(start, s["start"])) for s in audio_activity["speech_segments"])
            silent = end - start - voiced
            if silent >= 0.5 and silent >= (end - start) * 0.5:
                non_speech_overlap.append(index)
        previous_start = start
    if invalid:
        issue("invalid_timestamps", "Một số timestamps không có giá trị thời gian hợp lệ.", invalid)
    if outside:
        issue("timestamps_outside_audio", "Một số timestamps vượt ngoài thời lượng audio. Đã bỏ các chỉ số theo thời gian.", outside)
    if reversed_order:
        issue("timestamps_reversed", "Thời điểm bắt đầu của một số từ bị lùi. Đã bỏ các chỉ số theo thời gian.", reversed_order)
    if zero_duration:
        issue("zero_word_duration", "Một số từ có thời lượng bằng 0. Đã bỏ metrics theo timestamps STT.", zero_duration)
    if long_duration:
        issue("long_word_duration", "Một số từ được gán thời lượng từ 1,5 giây. Cần kiểm tra căn chỉnh audio.", long_duration, severity="warning")
    if non_speech_overlap:
        issue("word_overlaps_non_speech", "Một số từ bao gồm khoảng audio không được VAD nhận là giọng nói. Timestamps cần kiểm tra.", non_speech_overlap, severity="warning")
    if words and not invalid and tokens(" ".join(w["word"] for w in words)) != transcript_tokens:
        issue("transcript_word_mismatch", "Nội dung transcript và danh sách từ không khớp. Cần kiểm tra trước khi sử dụng metrics.")
    duration = words[-1].get("end", 0) - words[0].get("start", 0) if words and not invalid else 0
    if words and not invalid and duration <= 0:
        issue("zero_speech_duration", "Khoảng thời gian lời nói không hợp lệ.")

    text_blockers = {"empty_transcript", "repeated_content", "repeated_short_sentences", "transcript_word_mismatch", "timestamps_outside_audio", "invalid_timestamps", "zero_word_duration"}
    text_checks_passed = not any(i["code"] in text_blockers for i in issues)
    timing_valid = text_checks_passed and not any(i["severity"] == "error" for i in issues) and bool(words)
    timing = None
    if timing_valid:
        raw = fluency_metrics(words)
        timing = {
            "speech_seconds": raw["thoi_luong_giay"],
            "words_per_minute": raw["toc_do_tu_moi_phut"],
            "pause_count": raw["so_lan_ngung"],
            "pause_seconds": raw["tong_thoi_gian_ngung"],
            "longest_pause_seconds": raw["ngung_dai_nhat"],
            "pauses": raw["cac_lan_ngung"],
        }
    # 'Like' often has a lexical meaning; don't treat it as a filler by default.
    filler_candidates = FILLERS - {"like"} | {"hmmm", "uhhh", "ummm"}
    activity = dict(audio_activity) if audio_activity else None
    word_count = len(words) if words else len(transcript_tokens)
    if activity and activity["status"] == "ok":
        window = activity["speech_window_seconds"]
        activity["words_per_minute"] = round(word_count * 60 / window, 1) if text_checks_passed and window else None
    elif activity:
        issue("vad_no_speech" if activity["status"] == "no_speech" else "vad_unavailable",
              "VAD chưa xác định được vùng giọng nói hợp lệ. Chỉ số audio chưa có.", severity="warning")
    return {
        "quality": {"status": "ok" if not issues else "needs_review",
                    "timing_valid": timing_valid, "issues": issues,
                    "text_checks_passed": text_checks_passed,
                    "evidence_review_word_indices": sorted({j for i in issues for j in i["word_indices"]}),
                    "repeated_sentences": repeated},
        "metrics": {"word_count": word_count,
                    "filler_count": sum(t in filler_candidates for t in transcript_tokens),
                    "adjacent_repetitions": [t for before, t in zip(transcript_tokens, transcript_tokens[1:]) if before == t],
                    "timing": timing, "audio_timing": activity,
                    "disfluency_candidates": disfluency_candidates(transcript)},
    }
