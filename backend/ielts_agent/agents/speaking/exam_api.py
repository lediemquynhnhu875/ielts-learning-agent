"""Local exam API. Session UUIDs are private capability URLs, not user accounts."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from io import BytesIO
import time
import wave
from typing import Literal
from uuid import UUID, uuid4

from fastapi import File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ielts_agent.agents.speaking.assessment import CRITERIA, answer_flags, compute_overall
from ielts_agent.agents.speaking.grading import capabilities, grade_session
from ielts_agent.agents.speaking.questions import CUE_CARDS
from ielts_agent.agents.speaking.sessions import SessionStore, advance, check_answer_mode, make_session
from ielts_agent.agents.speaking.database import export_database, public_answer, question_id as database_question_id
from ielts_agent.agents.speaking.planning import weakness_profile


store = SessionStore()

# Assets are stamped with their own mtime, so a reloaded page can never keep
# running a script the browser cached before an edit.
ASSETS = ("exam.js", "exam.css", "styles.css", "app.js", "feedback.js")


def stamped_page(path):
    html = path.read_text(encoding="utf-8")
    for name in ASSETS:
        asset = path.parent / name
        if asset.exists():
            html = html.replace(f"/static/{name}", f"/static/{name}?v={int(asset.stat().st_mtime)}")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


class NewSession(BaseModel):
    # A mock exam is spoken, so voice is the only mode it accepts; text belongs to
    # practice sessions. speaking.sessions.check_answer_mode holds the rule.
    mode: Literal["voice", "text"] = "voice"
    topic_id: str = "part2-skill"
    save_audio: bool = False
    learner_id: UUID | None = None
    kind: Literal["practice", "mock"] = "mock"
    thread_id: str | None = Field(default=None, min_length=1, max_length=200)


class Answer(BaseModel):
    question_id: str
    request_id: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=16000)


class TeacherReview(BaseModel):
    """UC03 reconciliation. This demo has no teacher accounts: the endpoint is
    loopback-only and the session UUID is the whole capability, so it must not be
    exposed publicly as a teacher interface."""

    teacher_id: UUID
    action: Literal["approve", "edit", "reject"]
    note: str = Field(default="", max_length=2000)
    bands: dict[Literal["FC", "LR", "GRA", "PR"], float | None] | None = None


class Action(BaseModel):
    action: Literal["pause", "resume", "prepare", "speak", "preview_part3", "use_voice"]
    version: int = Field(ge=0)


class AssessmentRequest(BaseModel):
    force: bool = False


class AudioPreference(BaseModel):
    enabled: bool
    version: int = Field(ge=0)


def read(db, session_id):
    try:
        return store.read(db, session_id)
    except KeyError:
        raise HTTPException(404, "Không tìm thấy phiên thi.") from None


def checked(db, session_id, version, question_id=None):
    state = read(db, session_id)
    if state["version"] != version:
        raise HTTPException(409, "Phiên đã thay đổi. Tải lại phiên trước khi gửi tiếp.")
    if state["status"] != "in_progress":
        raise HTTPException(409, "Phiên đã tạm dừng hoặc kết thúc.")
    if question_id is not None and question_id not in {state["current_question"]["q_id"], database_question_id(state["current_question"])}:
        raise HTTPException(409, "Câu trả lời không thuộc câu hỏi hiện tại.")
    return state


def snapshot(db, state):
    answers = store.answers(db, state["session_id"])
    return {"session": store.public(state),
            "answers": [public_answer(a, state, i) for i, a in enumerate(answers, 1)],
            "capabilities": capabilities()}


def commit_answer(session_id, request_id, version, question_id, text, analysis, audio=None, mime=None):
    with store.connection() as db:
        duplicate = db.execute("SELECT content FROM answers WHERE session_id=? AND request_id=?", (session_id, request_id)).fetchone()
        if duplicate:
            prior = json.loads(duplicate[0])
            if question_id not in {prior["question"]["q_id"], database_question_id(prior["question"])}:
                raise HTTPException(409, "Request ID đã dùng cho câu hỏi khác.")
            return snapshot(db, read(db, session_id))
        state = checked(db, session_id, version, question_id)
        if state["mode"] == "text" and not text.strip():
            raise HTTPException(422, "Hãy nhập câu trả lời.")
        answer_id = str(uuid4())
        flags = answer_flags(text)
        content = {
            "answer_id": answer_id, "turn_id": str(uuid4()), "question": deepcopy(state["current_question"]),
            "transcript_ref": f"answer:{answer_id}:v1", "transcript_version": 1,
            "transcript": text, "mode": state["mode"], "flags": flags,
            "duration_s": analysis["audio_sample_count"] / 16000 if analysis.get("audio_sample_count") is not None else analysis.get("audio_seconds"),
            "stt_confidence": analysis.get("stt_confidence"), "submitted_at": datetime.now(timezone.utc).isoformat(),
            "analysis": analysis, "audio_ref": answer_id if state["save_audio"] and audio is not None else None,
        }
        advance(state, content)
        state["version"] += 1
        db.execute("INSERT INTO answers VALUES (?,?,?,?,?,?)", (answer_id, session_id, request_id, json.dumps(content, ensure_ascii=False), audio if state["save_audio"] else None, mime if state["save_audio"] else None))
        store.write(db, state)
        return snapshot(db, state)


def teacher_bands(body, results, review):
    """Bands a teacher releases, with the choice recorded per criterion.

    'approve' accepts the machine pair: the mean when both graders scored the
    criterion, otherwise whichever single band exists. 'edit' takes the bands the
    teacher supplied. PR stays null unless the teacher sets it, because the
    pronunciation scale is still uncalibrated.
    """
    bands = {}
    for criterion in CRITERIA:
        pair = [row["band"] for role in ("A", "B") for row in (results.get(role) or {}).get("criteria", [])
                if row["criterion"] == criterion and type(row.get("band")) in (int, float)]
        supplied = (body.bands or {}).get(criterion)
        if body.action == "edit" and criterion in (body.bands or {}):
            if supplied is not None and not 0 <= supplied <= 9:
                raise HTTPException(422, "Band của giáo viên phải trong khoảng 0–9.")
            band, chosen, reason = supplied, "middle", "Giáo viên nhập trực tiếp."
        elif len(pair) == 2:
            band = round(sum(pair) / 2, 2)
            chosen = "middle" if pair[0] != pair[1] else "A"
            low, high = sorted(pair)
            reason = (f"Giáo viên chấp nhận khoảng A/B ({low}–{high})." if low != high
                      else f"Hai giám khảo cùng chấm {low}.")
        elif pair:
            band, chosen, reason = pair[0], "A", "Chỉ một giám khảo chấm được tiêu chí này."
        else:
            band, chosen, reason = None, "middle", "Không có band máy chấm cho tiêu chí này."
        if band is not None:
            bands[criterion] = band
        review["decisions"][criterion] = {"final_band": band, "chosen": chosen, "reason": reason}
    if not bands:
        raise HTTPException(422, "Không có tiêu chí nào để công bố điểm.")
    return bands


def resolve_assessment(assessment, review):
    """Assessment after a teacher decision; rejection stays pending."""
    resolved = dict(assessment)
    if review["action"] == "reject":
        resolved["status"] = "pending_teacher"
        resolved["grading_errors"] = [*assessment.get("grading_errors", []),
                                      "Giáo viên đã từ chối bản chấm này; chưa công bố điểm."]
        return resolved
    resolved["status"] = "final"
    # A criterion the teacher released is assessed by the teacher, even when the
    # machine pair was escalated without producing a usable band.
    resolved["criteria"] = [{**row, "band": review["bands"].get(row["criterion"], row.get("band")),
                             "status": "assessed" if review["bands"].get(row["criterion"]) is not None
                             else ("not_assessed" if row["criterion"] == "PR" else row.get("status")),
                             "band_source": "teacher"} for row in assessment["criteria"]]
    resolved["overall_band"] = review["overall_band"]
    resolved["limitations"] = (assessment.get("limitations", "") +
                               " Điểm cuối do giáo viên công bố, không phải trung bình máy chấm.").strip()
    resolved["teacher_note"] = review.get("note", "")
    return resolved


def install_exam_routes(app, root, process_audio, suffixes, max_bytes, slots, audio_info):
    @app.get("/exam")
    def exam_page():
        return stamped_page(root / "web" / "exam.html")

    @app.get("/api/exam/capabilities")
    def exam_capabilities():
        return capabilities()

    @app.post("/api/exam/sessions", status_code=201)
    def create_session(body: NewSession):
        if body.topic_id not in {c["id"] for c in CUE_CARDS}:
            raise HTTPException(422, "Cue card không tồn tại.")
        try:
            check_answer_mode(body.mode, body.kind)
        except ValueError as refusal:
            raise HTTPException(422, str(refusal)) from None
        state = make_session(body.mode, body.topic_id, body.save_audio,
                             str(body.learner_id) if body.learner_id else None, body.kind, body.thread_id)
        with store.connection() as db:
            store.write(db, state)
            return snapshot(db, state)

    @app.get("/api/exam/sessions/{session_id}")
    def get_session(session_id: str):
        with store.connection() as db:
            return snapshot(db, read(db, session_id))

    @app.post("/api/exam/sessions/{session_id}/actions")
    def act(session_id: str, body: Action):
        with store.connection() as db:
            state = read(db, session_id)
            if state["version"] != body.version:
                raise HTTPException(409, "Phiên đã thay đổi; hãy tải lại.")
            if body.action == "preview_part3":
                return {**snapshot(db, state), "message": "Không xem trước câu hỏi Part 3. Hãy tiếp tục câu hỏi hiện tại."}
            if state["status"] == "finished":
                raise HTTPException(409, "Phiên đã kết thúc.")
            if body.action == "use_voice":
                # A mock checkpoint written before the exam became voice-only is
                # otherwise unusable: it can be switched while nothing is answered.
                if state["mode"] == "voice":
                    raise HTTPException(409, "Phiên đã ở chế độ ghi âm.")
                if state["turns"]:
                    raise HTTPException(409, "Phiên đã có câu trả lời nên không đổi được chế độ. Hãy bắt đầu phiên mới.")
                state["mode"] = "voice"
            elif body.action == "pause" and state["status"] == "in_progress":
                state["status"], state["paused_at"] = "paused", time.time()
            elif body.action == "resume" and state["status"] == "paused":
                gap = time.time() - state["paused_at"]
                state["paused_seconds"] += gap
                if state.get("phase_deadline"):
                    state["phase_deadline"] += gap
                state["status"], state["paused_at"] = "in_progress", None
            elif body.action in {"prepare", "speak"} and state["status"] == "in_progress" and state["current_question"]["kind"] == "long_turn":
                if body.action == "prepare":
                    if state["phase"] != "ready":
                        raise HTTPException(409, "Giai đoạn chuẩn bị đã bắt đầu.")
                    state["phase"], state["phase_deadline"] = "preparing", time.time() + 60
                else:
                    if state["phase"] != "speaking":
                        state["phase"], state["phase_deadline"] = "speaking", time.time() + 120
            else:
                raise HTTPException(409, "Thao tác không phù hợp trạng thái phiên.")
            state["version"] += 1
            store.write(db, state)
            return snapshot(db, state)

    @app.post("/api/exam/sessions/{session_id}/text")
    def submit_text(session_id: str, body: Answer):
        with store.connection() as db:
            state = read(db, session_id)
            if state["mode"] != "text":
                raise HTTPException(422, "Phiên voice cần gửi audio.")
            # Checkpoints written before the mock exam became voice-only can still
            # be resumed; they must not accept typed answers either.
            if state.get("kind", "mock") == "mock":
                raise HTTPException(422, "Phiên thi thử chỉ nhận câu trả lời ghi âm.")
        return commit_answer(session_id, body.request_id, body.version, body.question_id, body.text,
                             {"transcript": body.text, "words": [], "stt_confidence": None,
                              "metrics": {"timing": None, "audio_timing": None}})

    @app.post("/api/exam/sessions/{session_id}/voice")
    async def submit_voice(session_id: str, audio: UploadFile = File(...), question_id: str = Form(...),
                           request_id: str = Form(..., min_length=1, max_length=80), version: int = Form(..., ge=0),
                           keep_fillers: bool = Form(False), vocabulary: str = Form("", max_length=400),
                           pronunciation_consent: bool = Form(False)):
        try:
            with store.connection() as db:
                state = read(db, session_id)
                duplicate = db.execute("SELECT content FROM answers WHERE session_id=? AND request_id=?", (session_id, request_id)).fetchone()
                if duplicate:
                    prior_question = json.loads(duplicate[0])["question"]
                    if question_id not in {prior_question["q_id"], database_question_id(prior_question)}:
                        raise HTTPException(409, "Request ID đã dùng cho câu hỏi khác.")
                    return snapshot(db, state)
                state = checked(db, session_id, version, question_id)
                if state["mode"] != "voice":
                    raise HTTPException(422, "Phiên text cần gửi văn bản.")
                question = {**state["current_question"], "part": int(state["part"][-1])}
            suffix = Path(audio.filename or "").suffix.lower()
            if suffix not in suffixes:
                raise HTTPException(415, "Định dạng audio chưa được hỗ trợ.")
            content = await audio.read(max_bytes + 1)
            if not content or len(content) > max_bytes:
                raise HTTPException(413 if content else 422, "Audio trống hoặc vượt giới hạn 24 MB.")
            # Only the cue-card long turn has a two-minute limit. Closing answers
            # still carry part=2 in the exam state but use the short-answer cap.
            pipeline_question = {**question, "part": 2 if question["kind"] == "long_turn" else 1}
            async with slots:
                analysis = await run_in_threadpool(process_audio, content, suffix, keep_fillers,
                                                   question["id"], 0, "", pipeline_question, vocabulary, pronunciation_consent)
            analysis["part"], analysis["question"] = question["part"], question
            return commit_answer(session_id, request_id, version, question_id, analysis["transcript"], analysis, content, audio.content_type)
        finally:
            await audio.close()

    @app.get("/api/exam/sessions/{session_id}/audio/{answer_id}")
    def saved_audio(session_id: str, answer_id: str, download: bool = False):
        with store.connection() as db:
            read(db, session_id)
            row = db.execute("SELECT audio,mime FROM answers WHERE id=? AND session_id=?", (answer_id, session_id)).fetchone()
            if not row or row[0] is None:
                raise HTTPException(404, "Audio không được lưu cho lượt này.")
            mime = row[1] or "application/octet-stream"
            suffix = {"audio/webm": ".webm", "audio/mp4": ".m4a", "video/mp4": ".mp4",
                      "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
                      "audio/ogg": ".ogg", "audio/flac": ".flac", "audio/x-m4a": ".m4a"}.get(mime.split(";")[0].strip(), ".bin")
            return Response(row[0], media_type=mime, headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'{"attachment" if download else "inline"}; filename="speaking-answer{suffix}"',
            })

    @app.post("/api/exam/sessions/{session_id}/audio-preference")
    def audio_preference(session_id: str, body: AudioPreference):
        with store.connection() as db:
            state = read(db, session_id)
            if state["mode"] != "voice" or state["status"] == "finished":
                raise HTTPException(409, "Chỉ đổi lưu audio trong phiên ghi âm chưa kết thúc.")
            if state["version"] != body.version:
                raise HTTPException(409, "Phiên đã thay đổi; hãy tải lại.")
            state["save_audio"] = body.enabled
            state["version"] += 1
            store.write(db, state)
            return snapshot(db, state)

    @app.get("/api/exam/sessions/{session_id}/assessment-history")
    def assessment_history(session_id: str):
        with store.connection() as db:
            read(db, session_id)
            return {"history": [{"id": row[0], "created_at": row[1], **json.loads(row[2])}
                                for row in db.execute("SELECT id,created_at,content FROM grading_history WHERE session_id=? ORDER BY rowid DESC", (session_id,))]}

    @app.post("/api/exam/sessions/{session_id}/assessment")
    def assess(session_id: str, body: AssessmentRequest | None = None):
        force = bool(body and body.force)
        with store.connection() as db:
            state = read(db, session_id)
            if state["status"] != "finished":
                raise HTTPException(409, "Hoàn thành phiên trước khi chấm.")
            existing = db.execute("SELECT content FROM grading WHERE session_id=?", (session_id,)).fetchone()
            if existing and not force:
                return json.loads(existing[0])
            previous = existing[0] if existing else None
            reviewed = db.execute("SELECT content FROM reviews WHERE session_id=?", (session_id,)).fetchone()
            previous_review = reviewed[0] if reviewed else None
            answers = store.answers(db, session_id)
        result = grade_session(state, answers)
        with store.connection() as db:
            existing = db.execute("SELECT content FROM grading WHERE session_id=?", (session_id,)).fetchone()
            if existing and not force:
                return json.loads(existing[0])
            reviewed = db.execute("SELECT content FROM reviews WHERE session_id=?", (session_id,)).fetchone()
            if (existing[0] if existing else None) != previous or (reviewed[0] if reviewed else None) != previous_review:
                raise HTTPException(409, "Kết quả đã được chấm hoặc duyệt trong lúc chờ; hãy tải lại trước khi chấm lại.")
            state = read(db, session_id)
            valid_pair = len(result.get("graders", [])) == 2 and all(g.get("valid") for g in result["graders"])
            if force and previous and (result.get("retryable") or not valid_pair):
                state["last_grading_attempt"] = {
                    "status": "failed", "run_id": result["assessment"].get("run_id"),
                    "at": datetime.now(timezone.utc).isoformat(),
                    "message": "Chấm lại chưa thành công. Đang hiển thị kết quả cũ.",
                    "errors": result["assessment"].get("grading_errors", []),
                    "diagnostics": [{"role": g.get("grader_role"), "valid": g.get("valid"),
                                     "errors": [a.get("errors", []) for a in g.get("attempts", [])],
                                     "error_types": [a.get("error_type") for a in g.get("attempts", [])],
                                     "http_status": [a.get("http_status") for a in g.get("attempts", [])]}
                                    for g in result.get("graders", [])],
                }
                store.write(db, state)
                return {**json.loads(previous), "assessment": state["assessment"], "regrade_failed": True,
                        "message": "Chưa chấm lại thành công; kết quả trước được giữ nguyên.",
                        "last_grading_attempt": state["last_grading_attempt"],
                        "regrade_errors": result["assessment"].get("grading_errors", [])}
            if force and previous:
                archived = {"grading": json.loads(previous), "assessment": state["assessment"],
                            "teacher_review": json.loads(previous_review) if previous_review else None}
                db.execute("INSERT INTO grading_history VALUES (?,?,?,?)",
                           (str(uuid4()), session_id, json.dumps(archived, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
                db.execute("DELETE FROM reviews WHERE session_id=?", (session_id,))
            state["assessment"] = result["assessment"]
            state["last_grading_attempt"] = {
                "status": "completed" if valid_pair else "failed",
                "run_id": result["assessment"].get("run_id"), "at": datetime.now(timezone.utc).isoformat(),
                "message": "Đã chấm xong bằng hai giám khảo." if valid_pair else "Chưa có hai bản chấm hợp lệ. Hãy xem thông báo lỗi bên dưới.",
                "errors": result["assessment"].get("grading_errors", []) if not valid_pair else [],
            }
            result["last_grading_attempt"] = state["last_grading_attempt"]
            # Neither a missing configuration nor a provider/rate-limit failure is
            # cached: those are retryable, and caching one would freeze a session
            # that was never actually graded.
            if result["graders"] and not result.get("retryable"):
                db.execute("INSERT OR REPLACE INTO grading VALUES (?,?)", (session_id, json.dumps(result, ensure_ascii=False)))
            store.write(db, state)
        return result

    @app.get("/api/exam/sessions/{session_id}/weakness-profile")
    def learner_weakness_profile(session_id: str):
        """Derived view for the Planning Agent; it writes nothing by itself."""
        with store.connection() as db:
            state = read(db, session_id)
            answers = store.answers(db, session_id)
            graded = db.execute("SELECT content FROM grading WHERE session_id=?", (session_id,)).fetchone()
            reviewed = db.execute("SELECT content FROM reviews WHERE session_id=?", (session_id,)).fetchone()
            grading = json.loads(graded[0]) if graded else None
            if grading and reviewed:
                grading = {**grading, "teacher_review": json.loads(reviewed[0]),
                           "assessment": state["assessment"]}
            return weakness_profile(state, answers, grading)

    @app.post("/api/exam/sessions/{session_id}/teacher-review")
    def teacher_review(session_id: str, body: TeacherReview):
        """Resolve a pending_teacher run; a teacher decision supersedes A/B."""
        with store.connection() as db:
            state = read(db, session_id)
            graded = db.execute("SELECT content FROM grading WHERE session_id=?", (session_id,)).fetchone()
            if not graded:
                raise HTTPException(409, "Chưa có bản chấm nào để giáo viên xem lại.")
            if db.execute("SELECT 1 FROM reviews WHERE session_id=?", (session_id,)).fetchone():
                raise HTTPException(409, "Phiên này đã có kết quả giáo viên.")
            grading = json.loads(graded[0])
            assessment = grading["assessment"]
            review = {"teacher_id": str(body.teacher_id), "action": body.action, "note": body.note,
                      "at": datetime.now(timezone.utc).isoformat(), "decisions": {}, "bands": {},
                      "overall_band": None}
            results = {g["grader_role"]: g.get("result") for g in grading.get("graders", [])}
            if body.action in {"approve", "edit"}:
                review["bands"] = teacher_bands(body, results, review)
                review["overall_band"] = compute_overall(
                    [{"criterion": c, "band": b} for c, b in review["bands"].items()], state["mode"])
            db.execute("INSERT INTO reviews VALUES (?,?)", (session_id, json.dumps(review, ensure_ascii=False)))
            resolved = resolve_assessment(assessment, review)
            state["assessment"] = resolved
            store.write(db, state)
            return {"assessment": resolved, "teacher_review": review}

    @app.get("/api/exam/sessions/{session_id}/export")
    def export_session(session_id: str):
        with store.connection() as db:
            state = read(db, session_id)
            answers = store.answers(db, session_id)
            graded = db.execute("SELECT content FROM grading WHERE session_id=?", (session_id,)).fetchone()
            reviewed = db.execute("SELECT content FROM reviews WHERE session_id=?", (session_id,)).fetchone()
            saved_count = db.execute("SELECT count(*) FROM answers WHERE session_id=? AND audio IS NOT NULL", (session_id,)).fetchone()[0]
            audio_uri = f"/api/exam/sessions/{session_id}/attempt-audio" if answers and saved_count == len(answers) and state["mode"] == "voice" else None
            return export_database(state, answers, json.loads(graded[0]) if graded else None, audio_uri,
                                   json.loads(reviewed[0]) if reviewed else None)

    @app.get("/api/exam/sessions/{session_id}/attempt-audio")
    def attempt_audio(session_id: str):
        with store.connection() as db:
            state = read(db, session_id)
            rows = db.execute("SELECT audio FROM answers WHERE session_id=? ORDER BY rowid", (session_id,)).fetchall()
            if state["mode"] != "voice" or not rows or any(row[0] is None for row in rows):
                raise HTTPException(404, "Chưa có audio được đồng ý lưu cho toàn bộ lượt làm.")
        output = BytesIO()
        with wave.open(output, "wb") as combined:
            combined.setnchannels(1)
            combined.setsampwidth(2)
            combined.setframerate(16000)
            for (content,) in rows:
                _, samples = audio_info(content)
                combined.writeframes((samples.clip(-1, 1) * 32767).astype("<i2").tobytes())
        return Response(output.getvalue(), media_type="audio/wav", headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="speaking-attempt.wav"'})
