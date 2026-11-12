"""Database-facing Speaking records from database-design.docx (ERD 1/2).

SQLite checkpoints and provider payloads are implementation details. Only rows
in `tables` are database records; metrics and UI feedback live in `extensions`.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "ielts-speaking-db-1.0"


def stable_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return str(uuid5(NAMESPACE_URL, "ielts-speaking:" + str(value)))


def attempt_id(state):
    return state.get("attempt_id") or stable_id("attempt:" + state["session_id"])


def item_id(state):
    return state.get("item_id") or stable_id("content:" + state["session_id"])


def point_id(point):
    return point.get("id") or stable_id(f"point:{point['source_turn']}:{point['point']}")


def question_id(question):
    return question.get("question_id") or stable_id("question:" + question["q_id"])


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Learner(Record):
    id: UUID


class Session(Record):
    id: UUID
    learner_id: UUID
    kind: Literal["placement", "practice", "mock"]
    status: Literal["in_progress", "paused", "finished"]
    thread_id: str


class ContentItem(Record):
    item_id: UUID
    skill: Literal["Speaking"] = "Speaking"
    question_type: str
    topic: str
    target_band: float | None
    source: Literal["self_written", "llm_generated_verified", "open_license"]
    license: str
    author: str
    model: str | None
    prompt_version: str | None
    status: Literal["verified", "rejected", "spare"]
    body: dict
    created_at: datetime


class Question(Record):
    id: UUID
    item_id: UUID
    question_type: str
    answer_key: dict | None
    evidence_span: str | None
    excluded: bool


class Attempt(Record):
    attempt_id: UUID
    session_id: UUID
    item_id: UUID
    skill: Literal["Speaking"] = "Speaking"
    mode: Literal["text", "voice"]
    text_or_transcript: str
    audio_uri: str | None
    audio_deleted_at: datetime | None
    submitted_at: datetime | None
    raw_score: float | None


class Answer(Record):
    id: UUID
    attempt_id: UUID
    question_id: UUID
    block_no: int
    response: str
    is_correct: bool | None


class SpeakingTurn(Record):
    id: UUID
    attempt_id: UUID
    turn_no: int
    part: Literal["part1", "part2", "part3"]
    transcript: str
    stt_confidence: float | None = Field(ge=0, le=1)
    duration_s: float | None = Field(ge=0)
    t_start_s: float | None = Field(ge=0)


class CandidatePoint(Record):
    id: UUID
    turn_id: UUID
    point: str


class AskedQuestion(Record):
    id: UUID
    attempt_id: UUID
    part: Literal["part1", "part2", "part3"]
    text: str
    refs_point_id: UUID | None


class Assessment(Record):
    run_id: UUID
    attempt_id: UUID
    purpose: Literal["live", "eval"]
    status: Literal["final", "provisional", "pending_teacher", "failed"]
    overall_band: float | None
    word_count: int
    limitations: str
    descriptors_version: str | None
    trace_id: str | None
    cost_usd: float | None
    latency_ms: int | None


class Grading(Record):
    id: UUID
    run_id: UUID
    grader_role: Literal["A", "B"]
    model: str | None
    prompt_version: str | None
    trace_id: str | None


class GradingCriterion(Record):
    id: UUID
    grading_id: UUID
    criterion: Literal["FC", "LR", "GRA", "PR"]
    band: float | None = Field(ge=0, le=9)
    band_raw: float | None
    cap_reason: str | None
    comment: str


class EvidenceSpan(Record):
    id: UUID
    criterion_id: UUID
    start_char: int
    end_char: int
    t_start_s: float | None
    quote: str
    verified: bool


class DescriptorChunk(Record):
    chunk_id: str
    test_part: str
    criterion: Literal["FC", "LR", "GRA", "PR"]
    band: int | None
    version: str
    source_url: str | None


class GradingChunk(Record):
    grading_id: UUID
    chunk_id: str


class CriterionRef(Record):
    criterion_id: UUID
    chunk_id: str


class AssessmentFlag(Record):
    id: UUID
    run_id: UUID
    flag: Literal["under_length", "off_topic", "possible_plagiarism", "injection_detected", "too_short", "language_switch", "low_stt_confidence"]
    set_by: Literal["code", "judge"]
    details: dict


class Reconciliation(Record):
    id: UUID
    run_id: UUID
    model: str | None
    prompt_version: str | None
    trace_id: str | None
    self_confidence: Literal["low", "medium", "high"] | None
    escalated: bool
    escalate_reason: str | None


class ReconCriterion(Record):
    id: UUID
    reconciliation_id: UUID
    criterion: Literal["FC", "LR", "GRA", "PR"]
    final_band: float | None
    chosen: Literal["A", "B", "middle"]
    reason: str


class TeacherReview(Record):
    id: UUID
    run_id: UUID
    teacher_id: UUID
    action: Literal["approve", "edit", "reject"]
    note: str
    at: datetime


class FinalScore(Record):
    id: UUID
    run_id: UUID
    reconciliation_id: UUID | None
    review_id: UUID | None
    criterion: Literal["FC", "LR", "GRA", "PR", "overall"]
    band: float = Field(ge=0, le=9)
    status: Literal["final", "provisional", "pending_teacher"]
    source: Literal["average", "moderator", "teacher"]
    visible_to_learner: bool
    version: int


TABLE_MODELS = {
    "LEARNER": Learner, "SESSION": Session, "CONTENT_ITEM": ContentItem,
    "QUESTION": Question, "ATTEMPT": Attempt, "ANSWER": Answer,
    "SPEAKING_TURN": SpeakingTurn, "CANDIDATE_POINT": CandidatePoint,
    "ASKED_QUESTION": AskedQuestion, "ASSESSMENT": Assessment,
    "GRADING": Grading, "GRADING_CRITERION": GradingCriterion,
    "EVIDENCE_SPAN": EvidenceSpan, "DESCRIPTOR_CHUNK": DescriptorChunk,
    "GRADING_CHUNK": GradingChunk, "CRITERION_REF": CriterionRef,
    "ASSESSMENT_FLAG": AssessmentFlag, "RECONCILIATION": Reconciliation,
    "RECON_CRITERION": ReconCriterion, "TEACHER_REVIEW": TeacherReview, "FINAL_SCORE": FinalScore,
}


def public_question(question, state):
    if question is None:
        return None
    point = question.get("candidate_point_ref")
    result = {k: v for k, v in question.items() if k not in {"id", "q_id", "candidate_point_ref"}}
    result.update(id=question["q_id"], question_id=question_id(question),
                  attempt_id=attempt_id(state), bank_question_id=question["id"],
                  refs_point_id=point_id(point) if point else None)
    return result


def public_answer(answer, state, turn_no):
    return {
        "id": answer["answer_id"], "attempt_id": attempt_id(state),
        "question_id": question_id(answer["question"]), "block_no": turn_no,
        "response": answer["transcript"], "is_correct": None,
        "speaking_turn": {"id": answer["turn_id"], "attempt_id": attempt_id(state),
                          "turn_no": turn_no, "part": answer["question"]["part"],
                          "transcript": answer["transcript"], "stt_confidence": answer.get("stt_confidence"),
                          "duration_s": answer.get("duration_s"), "t_start_s": answer.get("t_start_s")},
        "question": public_question(answer["question"], state),
        "analysis": answer["analysis"], "flags": answer["flags"],
        "audio_uri": f"/api/exam/sessions/{state['session_id']}/audio/{answer['answer_id']}" if answer.get("audio_ref") else None,
    }


def public_state(state):
    result = {k: v for k, v in state.items() if k not in {
        "plan", "short_prompts", "paused_at", "started_at", "finished_at", "paused_seconds",
        "session_id", "turns", "asked_questions", "candidate_points", "current_question",
    }}
    result.update(id=state["session_id"], attempt_id=attempt_id(state), item_id=item_id(state),
                  kind=state.get("kind", "mock"), thread_id=state.get("thread_id", state["session_id"]))
    result["current_question"] = public_question(state["current_question"], state)
    result["asked_questions"] = [public_question(q, state) for q in state["asked_questions"]]
    result["candidate_points"] = [{"id": point_id(p), "turn_id": p["source_turn"], "point": p["point"]} for p in state["candidate_points"]]
    result["speaking_turns"] = [
        {"id": t["turn_id"], "attempt_id": attempt_id(state), "turn_no": i,
         "stt_confidence": t.get("stt_confidence"), "duration_s": t.get("duration_s"),
         "t_start_s": t.get("t_start_s"), "flags": t.get("flags", [])}
        for i, t in enumerate(state["turns"], 1)]
    if result.get("assessment"):
        result["assessment"] = dict(result["assessment"])
        result["assessment"].pop("session_id", None)
        result["assessment"]["attempt_id"] = attempt_id(state)
    return result


def export_database(state, answers, grading=None, audio_uri=None, review=None):
    """Normalize one Speaking attempt; all char/time offsets are attempt-relative."""
    grading = grading or {}
    review = review or (grading.get("teacher_review") if grading else None)
    tables = {name: [] for name in TABLE_MODELS}
    extensions = {"analysis": [], "feedback": {}, "unmapped": [], "audio_segments": []}
    external_chunks = set()

    def add(table, **row):
        validated = TABLE_MODELS[table](**row).model_dump(mode="json")
        tables[table].append(validated)
        return validated

    sid, aid, iid = stable_id(state["session_id"]), attempt_id(state), item_id(state)
    add("LEARNER", id=stable_id(state["learner_id"]))
    add("SESSION", id=sid, learner_id=stable_id(state["learner_id"]),
        kind=state.get("kind", "mock"), status=state["status"],
        thread_id=state.get("thread_id", state["session_id"]))
    content_questions = []
    for q in state["asked_questions"]:
        qid = question_id(q)
        content_questions.append({"id": qid, "text": q["text"], "part": q["part"],
                                  "asked_question_id": stable_id(q["q_id"]),
                                  "points": q.get("points", []), "explain": q.get("explain"),
                                  "bank_question_id": q.get("id")})
        add("QUESTION", id=qid, item_id=iid, question_type=q["part"],
            answer_key=None, evidence_span=None, excluded=False)
        ref = q.get("candidate_point_ref")
        add("ASKED_QUESTION", id=stable_id(q["q_id"]), attempt_id=aid,
            part=q["part"], text=q["text"], refs_point_id=point_id(ref) if ref else None)
    # A session whose Part 3 stems came from the configured question model is
    # recorded as llm_generated_verified: verified by the code checks in
    # question_llm, not by a human reviewer, so status stays 'spare'.
    generated = [t for t in state.get("question_traces", []) if t.get("status") == "verified"]
    add("CONTENT_ITEM", item_id=iid, skill="Speaking", question_type="speaking_session",
        topic=state["topic_id"], target_band=None,
        source="llm_generated_verified" if generated else "self_written",
        license="unconfirmed", author="unconfirmed",
        model=generated[0].get("model") if generated else None,
        prompt_version=generated[0].get("prompt_version") if generated else None,
        status="spare", body={"questions": content_questions}, created_at=state["created_at"])

    char_offsets, time_offsets, pieces = {}, {}, []
    char_cursor, time_cursor = 0, 0.0
    for n, answer in enumerate(answers, 1):
        response = answer["transcript"]
        char_offsets[answer["answer_id"]] = char_cursor
        pieces.append(response)
        char_cursor += len(response) + 2  # immutable transcript joined by two LF
        start = round(time_cursor, 6) if audio_uri is not None else None
        time_offsets[answer["answer_id"]] = start
        duration = answer.get("duration_s")
        if duration is not None:
            time_cursor += duration
        add("ANSWER", id=stable_id(answer["answer_id"]), attempt_id=aid,
            question_id=question_id(answer["question"]), block_no=n,
            response=response, is_correct=None)
        add("SPEAKING_TURN", id=stable_id(answer["turn_id"]), attempt_id=aid,
            turn_no=n, part=answer["question"]["part"], transcript=response,
            stt_confidence=answer.get("stt_confidence"), duration_s=duration,
            t_start_s=start)
        extensions["analysis"].append({"answer_id": stable_id(answer["answer_id"]),
                                       "turn_id": stable_id(answer["turn_id"]),
                                       "analysis": answer["analysis"], "flags": answer["flags"]})
        if answer.get("audio_ref"):
            extensions["audio_segments"].append({"turn_id": stable_id(answer["turn_id"]),
                "audio_uri": f"/api/exam/sessions/{sid}/audio/{answer['answer_id']}",
                "submitted_at": answer.get("submitted_at")})
    full_text = "\n\n".join(pieces)
    submitted = datetime.fromtimestamp(state["finished_at"], timezone.utc) if state.get("finished_at") else None
    add("ATTEMPT", attempt_id=aid, session_id=sid, item_id=iid, skill="Speaking",
        mode=state["mode"], text_or_transcript=full_text, audio_uri=audio_uri,
        audio_deleted_at=None, submitted_at=submitted, raw_score=None)
    for point in state["candidate_points"]:
        add("CANDIDATE_POINT", id=point_id(point), turn_id=stable_id(point["source_turn"]), point=point["point"])

    assessment = grading.get("assessment") or state.get("assessment")
    if assessment:
        rid = stable_id(assessment["run_id"])
        descriptors = grading.get("descriptor_chunks", [])
        versions = sorted({d["version"] for d in descriptors})
        add("ASSESSMENT", run_id=rid, attempt_id=aid,
            purpose=assessment.get("purpose", "live"), status=assessment["status"],
            overall_band=assessment["overall_band"], word_count=len(full_text.split()),
            limitations=assessment["limitations"],
            descriptors_version=versions[0] if len(versions) == 1 else None,
            trace_id=assessment.get("trace_id"), cost_usd=assessment.get("cost_usd"),
            latency_ms=assessment.get("latency_ms"))
        for descriptor in descriptors:
            add("DESCRIPTOR_CHUNK", chunk_id=descriptor["chunk_id"], test_part=descriptor["test_part"],
                criterion=descriptor["criterion"], band=descriptor.get("band"), version=descriptor["version"],
                source_url=descriptor.get("source_url"))
        known_chunks = {d["chunk_id"] for d in tables["DESCRIPTOR_CHUNK"]}
        for judge in grading.get("graders", []):
            role = judge.get("grader_role") or ("A" if judge.get("grader_id") == "grader-a" else "B")
            gid = stable_id(judge.get("id") or f"grading:{rid}:{role}")
            add("GRADING", id=gid, run_id=rid, grader_role=role,
                model=judge.get("model"), prompt_version=judge.get("prompt_version"), trace_id=judge.get("trace_id"))
            for chunk in sorted(set(judge.get("retrieved_chunk_ids", []))):
                add("GRADING_CHUNK", grading_id=gid, chunk_id=chunk)
                if chunk not in known_chunks:
                    external_chunks.add(chunk)
            if not judge.get("valid"):
                extensions["unmapped"].append({"grading_id": gid, "validation_attempts": judge.get("attempts", [])})
                continue
            for criterion in judge["result"]["criteria"]:
                cid = stable_id(f"criterion:{gid}:{criterion['criterion']}")
                add("GRADING_CRITERION", id=cid, grading_id=gid, criterion=criterion["criterion"],
                    band=criterion["band"], band_raw=criterion.get("band_raw", criterion["band"]),
                    cap_reason=criterion.get("cap_reason") or ("not_assessed" if criterion["band"] is None else None),
                    comment=criterion["comment"])
                for chunk in sorted(set(criterion.get("descriptor_refs", []))):
                    add("CRITERION_REF", criterion_id=cid, chunk_id=chunk)
                    if chunk not in known_chunks:
                        external_chunks.add(chunk)
                for index, span in enumerate(criterion.get("evidence", [])):
                    source = next((a for a in answers if a["answer_id"] == span.get("answer_id")), None)
                    start, end = span.get("start_char"), span.get("end_char")
                    if source is None or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source["transcript"]) or source["transcript"][start:end] != span.get("quote"):
                        raise ValueError("Cannot export invalid evidence quote/offset/reference")
                    offset = char_offsets[source["answer_id"]]
                    t0, local_time = time_offsets[source["answer_id"]], span.get("t_start_s")
                    timestamp = round(t0 + local_time, 6) if t0 is not None and local_time is not None else None
                    add("EVIDENCE_SPAN", id=stable_id(f"evidence:{cid}:{index}"), criterion_id=cid,
                        start_char=offset + start, end_char=offset + end, t_start_s=timestamp,
                        quote=span["quote"], verified=True)
        code_flags = {flag for a in answers for flag in a["flags"]}
        for flag in sorted(set(assessment.get("flags", [])) | code_flags):
            add("ASSESSMENT_FLAG", id=stable_id(f"flag:{rid}:{flag}"), run_id=rid, flag=flag,
                set_by="code" if flag in code_flags else "judge",
                details={"turn_ids": [stable_id(a["turn_id"]) for a in answers if flag in a["flags"]]})
        escalated = assessment["status"] == "pending_teacher" or bool(review)
        reconciliation_id = None
        if escalated:
            reconciliation_id = stable_id("reconciliation:" + rid)
            add("RECONCILIATION", id=reconciliation_id, run_id=rid,
                model=None, prompt_version=None, trace_id=None, self_confidence=None,
                escalated=True, escalate_reason="; ".join(assessment.get("grading_errors", [])) or "Teacher review required")
        review_id = None
        if review:
            review_id = stable_id(f"review:{rid}:{review['teacher_id']}:{review['at']}")
            add("TEACHER_REVIEW", id=review_id, run_id=rid, teacher_id=stable_id(review["teacher_id"]),
                action=review["action"], note=review.get("note", ""), at=review["at"])
            for criterion, decision in sorted(review.get("decisions", {}).items()):
                add("RECON_CRITERION", id=stable_id(f"recon:{reconciliation_id}:{criterion}"),
                    reconciliation_id=reconciliation_id, criterion=criterion,
                    final_band=decision.get("final_band"), chosen=decision["chosen"],
                    reason=decision.get("reason", ""))
        # Unassessed PR is represented by a NULL GRADING_CRITERION, never 0 or
        # a fake learner-visible FINAL_SCORE. Pending scores are withheld.
        valid_pair = len(grading.get("graders", [])) == 2 and all(g.get("valid") for g in grading["graders"])
        released = review["bands"] if review and review["action"] in {"approve", "edit"} else None
        if released is not None:
            # A teacher's decision supersedes the machine pair, including a pair
            # that disagreed too much to be averaged.
            for criterion, band in [*sorted(released.items()), ("overall", review.get("overall_band"))]:
                if band is not None:
                    add("FINAL_SCORE", id=stable_id(f"score:{rid}:{criterion}:2"), run_id=rid,
                        reconciliation_id=reconciliation_id, review_id=review_id, criterion=criterion,
                        band=band, status="final", source="teacher", visible_to_learner=True, version=2)
        elif valid_pair and assessment["status"] in {"final", "provisional"}:
            scores = [(row["criterion"], row["band"]) for row in assessment["criteria"]]
            scores.append(("overall", assessment["overall_band"]))
            for criterion, band in scores:
                if band is not None:
                    add("FINAL_SCORE", id=stable_id(f"score:{rid}:{criterion}:1"), run_id=rid,
                        reconciliation_id=None, review_id=None, criterion=criterion, band=band,
                        status=assessment["status"], source="average", visible_to_learner=True, version=1)
        extensions["feedback"] = {"run_id": rid, "corrections": assessment.get("corrections", []),
            "disclaimer": assessment.get("disclaimer"), "grading_errors": assessment.get("grading_errors", []),
            "criterion_statuses": {c["criterion"]: c.get("status") for c in assessment["criteria"]}}
    extensions["rag"] = grading.get("rag", {}) if grading else {}
    extensions["pronunciation"] = [{"answer_id": stable_id(a["answer_id"]), "turn_id": stable_id(a["turn_id"]),
                                    **a["analysis"]["pronunciation"]} for a in answers
                                   if a.get("analysis", {}).get("pronunciation")]
    extensions["rubric_text"] = grading.get("descriptor_chunks", []) if grading else []
    extensions["retrieval_traces"] = [{"grading_id": g["id"], "context": g.get("retrieval_context", {})} for g in grading.get("graders", [])] if grading else []
    extensions["checkpoint"] = public_state(state)
    extensions["question_engine"] = {"skipped_questions": state.get("skipped_questions", []),
                                     "traces": state.get("question_traces", [])}
    # Imported here: planning builds on this module's identifiers.
    from ielts_agent.agents.speaking.planning import weakness_profile

    extensions["weakness_profile"] = weakness_profile(state, answers, grading or None)
    result = {"schema_version": SCHEMA_VERSION, "tables": tables,
              "external_references": {"descriptor_chunk_ids": sorted(external_chunks)}, "extensions": extensions}
    validate_export(result)
    return result


def validate_export(payload):
    """Reject unknown columns, broken relationships and global quote offsets."""
    tables = payload["tables"]
    for name, rows in tables.items():
        if name not in TABLE_MODELS:
            raise ValueError(f"Unknown table {name}")
        for row in rows:
            TABLE_MODELS[name](**row)
    primary = {name: {row[next(iter(model.model_fields))] for row in tables[name]} for name, model in TABLE_MODELS.items() if name not in {"GRADING_CHUNK", "CRITERION_REF"}}
    for name, rows in tables.items():
        if name in primary and len(primary[name]) != len(rows):
            raise ValueError(f"Duplicate primary key in {name}")
    relations = {
        "SESSION": {"learner_id": "LEARNER"}, "QUESTION": {"item_id": "CONTENT_ITEM"},
        "ATTEMPT": {"session_id": "SESSION", "item_id": "CONTENT_ITEM"},
        "ANSWER": {"attempt_id": "ATTEMPT", "question_id": "QUESTION"},
        "SPEAKING_TURN": {"attempt_id": "ATTEMPT"}, "CANDIDATE_POINT": {"turn_id": "SPEAKING_TURN"},
        "ASKED_QUESTION": {"attempt_id": "ATTEMPT", "refs_point_id": "CANDIDATE_POINT"},
        "ASSESSMENT": {"attempt_id": "ATTEMPT"}, "GRADING": {"run_id": "ASSESSMENT"},
        "GRADING_CRITERION": {"grading_id": "GRADING"}, "EVIDENCE_SPAN": {"criterion_id": "GRADING_CRITERION"},
        "GRADING_CHUNK": {"grading_id": "GRADING"}, "CRITERION_REF": {"criterion_id": "GRADING_CRITERION"},
        "ASSESSMENT_FLAG": {"run_id": "ASSESSMENT"}, "RECONCILIATION": {"run_id": "ASSESSMENT"},
        "RECON_CRITERION": {"reconciliation_id": "RECONCILIATION"}, "TEACHER_REVIEW": {"run_id": "ASSESSMENT"},
        "FINAL_SCORE": {"run_id": "ASSESSMENT", "reconciliation_id": "RECONCILIATION", "review_id": "TEACHER_REVIEW"},
    }
    for table, fields in relations.items():
        for row in tables[table]:
            for field, parent in fields.items():
                if row[field] is not None and row[field] not in primary[parent]:
                    raise ValueError(f"Broken foreign key {table}.{field}")
    chunks = primary["DESCRIPTOR_CHUNK"] | set(payload["external_references"]["descriptor_chunk_ids"])
    for table in ("GRADING_CHUNK", "CRITERION_REF"):
        keys = [tuple(row.values()) for row in tables[table]]
        if len(set(keys)) != len(keys):
            raise ValueError(f"Duplicate composite primary key in {table}")
        for row in tables[table]:
            if row["chunk_id"] not in chunks:
                raise ValueError("Unknown descriptor chunk")
    assessment_attempt = {row["run_id"]: row["attempt_id"] for row in tables["ASSESSMENT"]}
    grading_run = {row["id"]: row["run_id"] for row in tables["GRADING"]}
    criterion_grading = {row["id"]: row["grading_id"] for row in tables["GRADING_CRITERION"]}
    transcripts = {row["attempt_id"]: row["text_or_transcript"] for row in tables["ATTEMPT"]}
    for row in tables["EVIDENCE_SPAN"]:
        run = grading_run[criterion_grading[row["criterion_id"]]]
        text = transcripts[assessment_attempt[run]]
        if not 0 <= row["start_char"] < row["end_char"] <= len(text) or text[row["start_char"]:row["end_char"]] != row["quote"]:
            raise ValueError("Evidence does not match ATTEMPT.text_or_transcript")


def practice_export(payload):
    """Adapt the browser-only Part 1/2 history to the same database contract."""
    session_id = payload["session_id"]
    state = {"session_id": session_id,
             "learner_id": payload.get("learner_id") or stable_id("local-learner:" + session_id),
             "kind": "practice", "thread_id": payload.get("thread_id") or session_id,
             "status": "in_progress", "mode": "voice", "topic_id": "practice-parts-1-2",
             "created_at": payload["created_at"], "asked_questions": [], "candidate_points": [],
             "turns": [], "current_question": None, "assessment": None}
    answers = []
    for n, raw in enumerate(payload["answers"], 1):
        question = dict(raw["question"])
        question.update(q_id=stable_id("practice-question:" + raw["id"]),
                        part=f"part{raw.get('part') or question.get('part', 1)}")
        if question["part"] not in {"part1", "part2", "part3"}:
            raise ValueError("Unknown Speaking part")
        state["asked_questions"].append(question)
        answer = {"answer_id": raw["id"], "turn_id": stable_id("practice-turn:" + raw["id"]),
                  "question": question, "transcript": raw["transcript"], "analysis": raw,
                  "flags": [], "duration_s": raw.get("audio_sample_count", 0) / 16000 if raw.get("audio_sample_count") is not None else raw.get("audio_seconds"),
                  "stt_confidence": raw.get("stt_confidence"), "audio_ref": None}
        answers.append(answer)
        state["turns"].append(answer)
    result = export_database(state, answers)
    result["extensions"]["unmapped"].append({"audio": "Browser practice audio is not persisted; audio_uri remains null."})
    return result
