"""UC04 assessment contract and executable evidence validation.

Descriptors are supplied by the group, never invented by the demo. No scores are
emitted unless two actual grader responses have passed validation.
"""

import math
import re
from uuid import uuid4

from ielts_agent.agents.speaking.analysis import tokens
from ielts_agent.agents.speaking.database import attempt_id


CRITERIA = ("FC", "LR", "GRA", "PR")
FLAGS = {"too_short", "off_topic", "language_switch", "low_stt_confidence", "injection_detected"}
INJECTION = re.compile(r"ignore\s+(?:all\s+)?(?:your|previous|the)\s+instructions|(?:system|assistant)\s*:|(?:give|set).{0,40}(?:band|criteria|score).{0,12}9", re.I)


def answer_flags(text):
    flags = []
    if len(text.split()) < 8:
        flags.append("too_short")
    if re.search(r"[ăâđêôơưĂÂĐÊÔƠƯ]|\b(?:tôi|không|tiếng|việt|mình)\b", text, re.I):
        flags.append("language_switch")
    if INJECTION.search(text):
        flags.append("injection_detected")
    return flags


def empty_assessment(session, reason):
    text_mode = session["mode"] == "text"
    return {
        "contract_version": "ielts-speaking-db-1.0", "run_id": str(uuid4()),
        "attempt_id": attempt_id(session), "mode": session["mode"], "purpose": "live",
        "trace_id": None, "cost_usd": None, "latency_ms": None,
        "assessment_scope": "full_session", "status": "provisional",
        "criteria": [{"criterion": c, "status": "not_assessed" if c == "PR" else "insufficient_evidence",
                      "band": None, "evidence": [], "descriptor_refs": [], "comment": reason}
                     for c in CRITERIA],
        "overall_band": None, "corrections": [],
        "flags": sorted({f for t in session["turns"] for f in t.get("flags", [])}),
        "limitations": ("Text: không đánh giá tốc độ, khoảng ngừng hoặc Pronunciation; điểm tổng từ 3 tiêu chí là tạm tính. "
                        if text_mode else "Feedback Azure tùy chọn được lưu riêng; band PR chưa hiệu chỉnh, chưa có tổng đủ 4 tiêu chí. ") + reason,
        "disclaimer": "Điểm ước lượng phục vụ luyện tập, không phải kết quả IELTS chính thức.",
        "grading_errors": [], "grader_refs": [],
    }


def quote_timestamp(answer, start_char):
    """Start second of the word that opens the quote, derived from STT words.

    Only called when the answer has valid timing, where analysis has already
    checked that the word list tokenizes to exactly the transcript tokens.
    """
    analysis = answer.get("analysis") or {}
    if session_timing_invalid(analysis):
        return None
    target = len(tokens(answer["transcript"][:start_char]))
    seen = 0
    for word in analysis.get("words") or []:
        seen += len(tokens(word.get("word") or ""))
        if seen > target:
            value = word.get("start")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return None
            limit = answer.get("duration_s")
            value = max(0.0, float(value))
            return round(min(value, float(limit)) if type(limit) in (int, float) else value, 3)
    return None


def session_timing_invalid(analysis):
    return not analysis.get("quality", {}).get("timing_valid") or not (analysis.get("words") or [])


def grammar_evidence_blocked(answer):
    """True when an answer's transcript text is too unreliable for GRA evidence."""
    quality = (answer.get("analysis") or {}).get("quality") or {}
    return quality.get("text_checks_passed") is False


def citable_for_grammar(answer):
    return answer is not None and not grammar_evidence_blocked(answer) and "low_stt_confidence" not in (answer.get("flags") or [])


def drop_unusable_grammar_evidence(result, answers):
    """Remove GRA quotes taken from transcripts that failed the STT text checks.

    Dropping those quotes keeps the rest of a valid assessment, while failing the
    whole attempt costs a re-grade the free token budget cannot spare. If nothing
    citable is left the row stays empty, so the validator still asks again.
    """
    dropped = []
    for row in result.get("criteria", []) if isinstance(result, dict) else []:
        if not isinstance(row, dict) or row.get("criterion") != "GRA" or not isinstance(row.get("evidence"), list):
            continue
        keep = [item for item in row["evidence"]
                if isinstance(item, dict) and citable_for_grammar(answers.get(item.get("answer_id")))]
        if keep and len(keep) < len(row["evidence"]):
            dropped += [item for item in row["evidence"] if item not in keep]
            row["evidence"] = keep
    return dropped


def resolve_evidence(result, session, answers):
    """Attach code-derived offsets and timestamps to the quotes a grader returned.

    Graders supply only answer_id and an exact quote. Character offsets and audio
    timestamps are located here by searching that answer's immutable transcript,
    so no model-reported offset is ever trusted. Quotes that are not present
    verbatim are reported as errors instead of being adjusted to fit.
    """
    errors = []
    if not isinstance(result, dict) or not isinstance(result.get("criteria"), list):
        return errors
    for row in result["criteria"]:
        if not isinstance(row, dict) or not isinstance(row.get("evidence"), list):
            continue
        criterion = row.get("criterion")
        for item in row["evidence"]:
            if not isinstance(item, dict):
                errors.append(f"{criterion}: evidence must be an object")
                continue
            answer_id = item.get("answer_id")
            answer = answers.get(answer_id) if isinstance(answer_id, str) else None
            quote = item.get("quote")
            if answer is None:
                errors.append(f"{criterion}: evidence must reference an answer_id from this session")
                continue
            if not isinstance(quote, str) or not tokens(quote):
                errors.append(f"{criterion}: evidence quote must contain words from the transcript")
                continue
            start = answer["transcript"].find(quote)
            if start < 0:
                errors.append(f"{criterion}: quote was not found verbatim in answer {answer_id}; copy a contiguous span of that transcript exactly")
                continue
            item.update(start_char=start, end_char=start + len(quote),
                        turn_id=answer["turn_id"], transcript_ref=answer["transcript_ref"],
                        transcript_version=1,
                        t_start_s=None if session["mode"] == "text" else quote_timestamp(answer, start))
    return errors


def validate_assessment(result, session, answers, descriptors):
    """Character offsets refer to Python Unicode code points, end-exclusive."""
    errors = []
    if not isinstance(result, dict):
        return ["Assessment must be an object"]
    rows = result.get("criteria")
    if not isinstance(rows, list) or len(rows) != 4 or any(not isinstance(r, dict) or not isinstance(r.get("criterion"), str) for r in rows) or {r["criterion"] for r in rows} != set(CRITERIA):
        return ["Exactly one entry for each FC/LR/GRA/PR is required"]
    catalog = {d["chunk_id"]: d for d in descriptors}
    for row in rows:
        criterion, band = row["criterion"], row.get("band")
        if criterion == "PR":
            # Explicit voice MVP policy; this is not UC04's pronunciation proxy.
            if band is not None or row.get("status") != "not_assessed":
                errors.append("PR must be not_assessed with band=null under current MVP policy")
            if row.get("evidence") or row.get("descriptor_refs"):
                errors.append("Unassessed PR must not contain scored evidence or descriptor refs")
            continue
        if isinstance(band, bool) or not isinstance(band, (float, int)) or not math.isfinite(band) or not 0 <= band <= 9:
            errors.append(f"{criterion}: band must be finite, 0–9")
        if row.get("status") != "assessed" or not isinstance(row.get("comment"), str) or not row["comment"].strip():
            errors.append(f"{criterion}: assessed status and comment required")
        refs = row.get("descriptor_refs")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or ref not in catalog or catalog[ref].get("test_part") != "speaking" or catalog[ref].get("criterion") != criterion for ref in refs):
            errors.append(f"{criterion}: invalid Speaking descriptor_refs")
        elif type(band) in (int, float) and math.isfinite(band):
            cited_bands = {catalog[ref].get("band") for ref in refs}
            if None not in cited_bands and not cited_bands.intersection({math.floor(band), math.ceil(band)}):
                errors.append(f"{criterion}: cite the assigned band descriptor, not just a different band")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{criterion}: evidence required")
            continue
        for item in evidence:
            if not isinstance(item, dict):
                errors.append(f"{criterion}: evidence must be an object")
                continue
            answer_id = item.get("answer_id")
            answer = answers.get(answer_id) if isinstance(answer_id, str) else None
            start, end = item.get("start_char"), item.get("end_char")
            quote = item.get("quote")
            if not answer or type(start) is not int or type(end) is not int or not isinstance(quote, str) or not quote or not 0 <= start < end <= len(answer["transcript"]) or answer["transcript"][start:end] != quote:
                errors.append(f"{criterion}: quote/offset/answer mismatch")
                continue
            if item.get("transcript_ref") != answer["transcript_ref"] or item.get("transcript_version") != 1:
                errors.append(f"{criterion}: transcript reference/version mismatch")
            if item.get("turn_id") != answer["turn_id"]:
                errors.append(f"{criterion}: turn reference mismatch")
            timestamp = item.get("t_start_s")
            if session["mode"] == "text" or not answer["analysis"].get("quality", {}).get("timing_valid"):
                if timestamp is not None:
                    errors.append(f"{criterion}: timestamp must be null")
            elif type(timestamp) not in (int, float) or not math.isfinite(timestamp) or not 0 <= timestamp <= answer["duration_s"]:
                errors.append(f"{criterion}: invalid timestamp")
            if criterion == "GRA" and "low_stt_confidence" in answer["flags"]:
                errors.append("GRA: low confidence answer cannot be used as grammar-error evidence")
            # Only transcript-text problems can turn an STT artefact into a false
            # grammar error. Timing warnings (word durations, reversed stamps)
            # leave the words themselves intact, and blocking on those made every
            # real voice session impossible to grade.
            if criterion == "GRA" and grammar_evidence_blocked(answer):
                errors.append("GRA: transcript text failed STT checks; it needs human audio verification before it can show grammar errors")
            if "injection_detected" in answer["flags"]:
                errors.append(f"{criterion}: injected answer requires human review")
    flags = result.get("flags", [])
    if not isinstance(flags, list) or any(not isinstance(f, str) or f not in FLAGS for f in flags):
        errors.append("Invalid flags")
    corrections = result.get("corrections")
    if not isinstance(corrections, list) or len(corrections) != 2:
        errors.append("Exactly two answer corrections required")
    else:
        ids = set()
        for correction in corrections:
            if not isinstance(correction, dict) or not isinstance(correction.get("answer_id"), str) or correction.get("answer_id") not in answers or not isinstance(correction.get("upgraded_answer"), str) or not correction["upgraded_answer"].strip() or not isinstance(correction.get("vocabulary"), list) or not correction["vocabulary"] or any(not isinstance(v, str) or not v.strip() for v in correction["vocabulary"]):
                errors.append("Invalid correction answer reference, upgraded answer or vocabulary")
            else:
                ids.add(correction["answer_id"])
        if len(ids) != 2:
            errors.append("Corrections must reference two distinct answers")
    return errors


def compute_overall(criteria, mode):
    required = CRITERIA[:3] if mode == "text" else CRITERIA
    bands = {row["criterion"]: row.get("band") for row in criteria}
    if any(type(bands.get(c)) not in (int, float) or not math.isfinite(bands[c]) or not 0 <= bands[c] <= 9 for c in required):
        return None
    # Technical policy: preserve two decimals; do not claim IELTS rounding.
    return round(sum(bands[c] for c in required) / len(required), 2)
