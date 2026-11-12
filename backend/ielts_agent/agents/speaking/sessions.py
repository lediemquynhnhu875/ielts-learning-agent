"""Local SQLite checkpoints and bounded, adaptive Speaking exam flow.

The question engine asks from transparent templates and extracts exact learner
sentences, with references, as candidate points. A Part 3 stem may instead be
written by an LLM when SPEAKING_QUESTION_MODEL is configured, but only after it
passes the code checks in question_llm; the templates remain the fallback.
Near-duplicate questions are rejected by local cosine similarity over question
stems, which catches reworded repeats but does not prove two questions differ
in meaning.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from uuid import uuid4

from ielts_agent.agents.speaking.assessment import answer_flags, empty_assessment
from ielts_agent.agents.speaking.questions import CUE_CARDS, question_bank
from ielts_agent.agents.speaking.database import public_state
from ielts_agent.agents.speaking.question_llm import generated_stem, semantic_duplicate
from ielts_agent.agents.speaking.similarity import NEAR_DUPLICATE, nearest


def now():
    return datetime.now(timezone.utc).isoformat()


def initial_plan(card):
    topics = question_bank()
    plan = [{**q, "part": "part1", "kind": "short"}
            for topic in topics[:2] for q in topic["questions"][:2]]
    plan += [{**card, "part": "part2", "kind": "long_turn"},
             {"id": "part2-closing", "part": "part2", "kind": "closing",
              "text": "Would you recommend this experience to someone else? Why?"}]
    themes = {
        "part2-skill": "learning useful skills", "part2-place": "tourism and public places",
        "part2-person": "helping others", "part2-object": "everyday technology and consumption",
        "part2-project": "teamwork in society", "part2-activity": "access to leisure activities",
    }
    plan += [{"id": f"part3-{i}", "part": "part3", "kind": "discussion", "intent": intent,
              "text": f"Why is {themes[card['id']]} important in society today?" if i == 0 else ""}
             for i, intent in enumerate(["importance", "compare", "hypothesis", "challenge"])]
    return plan


def grounding_quote(question):
    """The text a question quotes verbatim: a candidate point, or a prior question."""
    point = (question.get("candidate_point_ref") or {}).get("point")
    return question.get("quoted_text") or point


def question_stem(question):
    """The question without the text it quotes, i.e. what is actually being asked."""
    quote = grounding_quote(question)
    text = question["text"]
    return text.replace(quote, " ").replace("You said:", " ") if quote else text


def duplicate_of_asked(question, state):
    """Exact-text guard, then weighted cosine over stems that share a quote.

    Questions are only comparable when they quote the same thing. Several Part 3
    angles deliberately share one candidate point while asking different things,
    and several follow-up prompts share one template while quoting different
    questions; neither pair is a repeat.
    """
    normalized = " ".join(re.findall(r"\w+", question["text"].lower()))
    if any(" ".join(re.findall(r"\w+", q["text"].lower())) == normalized for q in state["asked_questions"]):
        return True, 1.0, "exact_text"
    quote = grounding_quote(question)
    comparable = [q for q in state["asked_questions"] if grounding_quote(q) == quote]
    score, match = nearest(question_stem(question), [question_stem(q) for q in comparable])
    return score >= NEAR_DUPLICATE, score, match


# Questions the engine constructs are also checked by the model when one is
# configured, because a reworded repeat can share almost no vocabulary and so
# score low on local cosine. Curated bank questions are trusted and pass through
# the local guard only.
CONSTRUCTED = {"discussion", "prompt"}


def ask(state, question, checker=None):
    """Ask a question unless it repeats one already asked.

    Returns False instead of raising: a rejected question must not abort the
    request that is committing the learner's answer.
    """
    duplicate, score, match = duplicate_of_asked(question, state)
    reason = "near_duplicate_question"
    # The model compares against every asked question, not only the ones sharing
    # a quote: a reworded repeat of an earlier question usually quotes nothing.
    if not duplicate and state["asked_questions"] and question.get("kind") in CONSTRUCTED:
        duplicate, trace = semantic_duplicate(question_stem(question),
                                              [question_stem(q) for q in state["asked_questions"]], checker)
        state.setdefault("question_traces", []).append({**trace, "similarity": score})
        reason = "semantic_duplicate_question" if duplicate else reason
    if duplicate:
        state.setdefault("skipped_questions", []).append(
            {"text": question["text"], "similarity": score, "closest_asked": match,
             "reason": reason})
        return False
    question = {**question, "q_id": str(uuid4()), "asked_at": now(),
                "dedup_similarity": score}
    state["current_question"] = question
    state["part"] = question["part"]
    state["asked_questions"].append(question)
    state["phase"] = "ready"
    state["phase_deadline"] = None
    return True


# UC04 is a speaking test, so a mock session only accepts recorded answers.
# Text mode stays available for single-question practice and for offline tests,
# where no transcript is produced by a provider.
def check_answer_mode(mode, kind):
    if kind == "mock" and mode != "voice":
        raise ValueError("Phiên thi thử chỉ nhận câu trả lời ghi âm. Chọn phiên luyện tập nếu muốn gõ chữ.")


def make_session(mode, card_id, save_audio, learner_id=None, kind="mock", thread_id=None):
    check_answer_mode(mode, kind)
    card = next(c for c in CUE_CARDS if c["id"] == card_id)
    state = {
        "session_id": str(uuid4()), "learner_id": learner_id or str(uuid4()), "mode": mode,
        "attempt_id": str(uuid4()), "item_id": str(uuid4()), "kind": kind,
        "thread_id": thread_id or str(uuid4()),
        "response_mode": "spontaneous", "topic_id": card_id,
        "part": "part1", "asked_questions": [], "candidate_points": [], "turns": [],
        "elapsed_seconds": 0, "part_time_left": None, "followup_count": 0,
        "turn_limit": 20, "status": "in_progress", "version": 0,
        "created_at": now(), "started_at": time.time(), "paused_seconds": 0,
        "paused_at": None, "save_audio": bool(save_audio and mode == "voice"),
        "plan": initial_plan(card), "plan_index": 0, "short_prompts": [],
        "notice": "", "policy_version": "speaking-mvp-0.2", "assessment": None,
        "skipped_questions": [], "question_traces": [],
    }
    ask(state, state["plan"][0])
    return state


def refreshed(state):
    wall = state.get("finished_at") or state.get("paused_at") or time.time()
    state["elapsed_seconds"] = max(0, int(wall - state["started_at"] - state["paused_seconds"]))
    deadline = state.get("phase_deadline")
    if deadline:
        remaining = max(0, int(deadline - wall))
        if state["phase"] == "preparing" and remaining == 0:
            state["phase"] = "speaking"
            state["phase_deadline"] = deadline + 120
            remaining = max(0, int(state["phase_deadline"] - wall))
        state["part_time_left"] = remaining
    else:
        state["part_time_left"] = None
    return state


def advance(state, answer):
    question = state["current_question"]
    flags = answer["flags"]
    state["turns"].append({k: answer[k] for k in ("turn_id", "answer_id", "transcript_ref", "stt_confidence", "duration_s", "flags")})
    state["notice"] = ""
    if "language_switch" in flags:
        state["notice"] = "Please continue in English."
    if "injection_detected" in flags:
        state["notice"] = "Chỉ dẫn trong câu trả lời được coi là dữ liệu; không thay đổi chính sách chấm."
    if not {"injection_detected", "language_switch", "too_short"}.intersection(flags):
        for sentence in re.split(r"(?<=[.!?])\s+", answer["transcript"].strip())[:3]:
            if sentence and not any(p["point"] == sentence and p["source_turn"] == answer["turn_id"] for p in state["candidate_points"]):
                state["candidate_points"].append({"point": sentence, "source_turn": answer["turn_id"], "part": question["part"]})
    if len(state["turns"]) >= state["turn_limit"]:
        finish(state)
        return
    key = str(state["plan_index"])
    if "too_short" in flags and key not in state["short_prompts"]:
        state["short_prompts"].append(key)
        extra = {**question, "id": question["id"] + "-expand", "kind": "prompt",
                 "quoted_text": question["text"],
                 "text": f"For the question ‘{question['text']}’, could you give a specific example and explain your reason?"}
        if ask(state, extra):
            state["followup_count"] += 1
            return
    # A question rejected as a near duplicate is skipped rather than reworded
    # until it happens to pass: keep moving through the plan, never repeat.
    while True:
        state["plan_index"] += 1
        if state["plan_index"] >= len(state["plan"]):
            finish(state)
            return
        next_q = build_question(state)
        if ask(state, next_q):
            if next_q["part"] == "part3" and next_q.get("candidate_point_ref"):
                state["followup_count"] += 1
            return
        state["notice"] = "Một câu hỏi đã bị bỏ vì trùng với câu đã hỏi."


# Asked when no candidate point could be extracted. Each intent needs its own
# wording: three sentences differing only by the intent word are one question.
UNGROUNDED = {
    "compare": "Thinking about this cue card topic, how might attitudes differ between younger and older people? Please give a reason.",
    "hypothesis": "Staying with the same topic, what would change for most people if the opposite were true? Please explain why.",
    "challenge": "Some people take the opposite view of this cue card topic. What would you say to them, and on what grounds?",
}

TEMPLATES = {
    "compare": "How might this differ between younger and older generations?",
    "hypothesis": "How would society change if the opposite were true?",
    "challenge": "What might someone who disagrees with this view say, and how would you respond?",
}


def build_question(state, caller=None):
    """The next planned question, grounded in a candidate point for Part 3."""
    next_q = dict(state["plan"][state["plan_index"]])
    if next_q["part"] != "part3" or next_q.get("intent") == "importance":
        return next_q
    # Prefer the latest Part 3 point, then the Part 2 long turn.
    pool = [p for p in state["candidate_points"] if p["part"] in ("part2", "part3")]
    if not pool:
        state["notice"] = "Chưa đủ ý trả lỏi để hỏi đào sâu; hãy bổ sung ví dụ cụ thể."
        next_q["text"] = UNGROUNDED[next_q["intent"]]
        next_q["grounding_status"] = "insufficient_candidate_points"
        return next_q
    point = pool[-1]
    stem, trace = generated_stem(next_q["intent"], state["topic_id"], point["point"],
                                 [question_stem(q) for q in state["asked_questions"]], caller)
    state.setdefault("question_traces", []).append({**trace, "plan_index": state["plan_index"]})
    # The quote is inserted by code, so the grounding sentence is always exactly
    # what the learner said even when the stem came from a model.
    next_q["text"] = f"You said: “{point['point']}” {stem or TEMPLATES[next_q['intent']]}"
    next_q["candidate_point_ref"] = point
    next_q["stem_source"] = "llm_generated_verified" if stem else "template"
    return next_q


def finish(state):
    state.update(status="finished", part="finished", current_question=None,
                 phase="finished", phase_deadline=None, finished_at=time.time())
    state["assessment"] = empty_assessment(state, "Chưa chạy hai giám khảo; không có điểm được tạo tự động từ metrics.")


class SessionStore:
    """Transactions serialize checkpoints; request IDs make retries idempotent."""

    def __init__(self, path=None):
        self._path = Path(path) if path else None

    @property
    def path(self):
        # Resolve after server dotenv initialization; an empty optional env var
        # must use the default rather than trying to open '.' as a database.
        return self._path or Path(os.environ.get("SPEAKING_DB_PATH") or Path(__file__).parent / "data" / "sessions.sqlite3")

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS answers (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, request_id TEXT NOT NULL, content TEXT NOT NULL, audio BLOB, mime TEXT, UNIQUE(session_id,request_id))")
            db.execute("CREATE TABLE IF NOT EXISTS grading (session_id TEXT PRIMARY KEY, content TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS reviews (session_id TEXT PRIMARY KEY, content TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS grading_history (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.commit()
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def read(self, db, session_id):
        row = db.execute("SELECT state FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise KeyError(session_id)
        return refreshed(json.loads(row[0]))

    def write(self, db, state):
        db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?)", (state["session_id"], json.dumps(refreshed(state), ensure_ascii=False)))

    def answers(self, db, session_id):
        return [json.loads(row[0]) for row in db.execute("SELECT content FROM answers WHERE session_id=? ORDER BY rowid", (session_id,))]

    def public(self, state):
        return public_state(refreshed(state))
