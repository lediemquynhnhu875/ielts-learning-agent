"""Giai đoạn 4: lắp văn bản LLM vào khung và nạp ra record database.

Mọi thứ ở đây do code quyết định: ID, thứ tự, timestamp, duration_s, t_start_s,
stt_confidence, cờ edge-case. LLM chỉ góp phần văn bản (mục 1 và 4).

Record dùng chính các model Pydantic của speaking/database.py nên sai schema là
lỗi ngay tại đây, không lọt xuống DB. ERD 2 (ASSESSMENT trở đi) KHÔNG sinh ở
đây: phải chạy pipeline chấm thật với purpose = eval.
"""

import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

import plan as planner          # noqa: E402
import qbank                    # noqa: E402
from ielts_agent.agents.speaking import database as db   # noqa: E402

OUT = HERE / "out"
PART = {1: "part1", 2: "part2", 3: "part3"}
SHORT_ANSWERS = ["Yes.", "I don't know.", "No, not really.", "Maybe."]


def words(text):
    return [w for w in re.findall(r"[^\W_]+(?:'[^\W_]+)?", text) if w]


def sample_confidence(rng, profile):
    value = rng.gauss(profile["mean"], profile["sd"])
    return round(min(profile["max"], max(profile["min"], value)), 3)


def turn_timing(rng, text, rate, band):
    """duration_s từ số từ và tốc độ nói, cộng thời gian ngắt nghỉ.

    Band thấp ngắt nhiều hơn, nên hệ số ngắt giảm dần theo band.
    """
    count = len(words(text))
    speaking = count / rate
    pause_factor = max(0.05, 0.42 - (band - 4.0) * 0.07)
    pause = speaking * pause_factor * rng.uniform(0.7, 1.3)
    return round(speaking + pause + rng.uniform(0.3, 1.2), 2)


def candidate_points(turns_rows, flags_by_turn):
    """Đúng rule của agent thật (speaking/sessions.py): 3 câu đầu mỗi lượt.

    Lượt bị gắn cờ injection_detected, language_switch hoặc too_short thì không
    trích ý, vì hệ thống thật cũng bỏ qua.
    """
    blocked = {"injection_detected", "language_switch", "too_short"}
    rows, seen = [], set()
    for turn in turns_rows:
        if blocked & set(flags_by_turn.get(str(turn["id"]), [])):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", turn["transcript"].strip())[:3]:
            sentence = sentence.strip()
            if not sentence or (str(turn["id"]), sentence) in seen:
                continue
            seen.add((str(turn["id"]), sentence))
            rows.append(db.CandidatePoint(
                id=db.stable_id(f"point:{turn['id']}:{sentence}"),
                turn_id=turn["id"], point=sentence))
    return rows


def build_attempt(spec, session, produced, rng, variant=None):
    """Một attempt Speaking đầy đủ: session, item, attempt, turn, point, question."""
    band = produced["intended_band"]
    profile = spec["band_profiles"][band]
    rate = profile["speech_rate"]
    group = (variant or {}).get("group")
    key = (variant or {}).get("key", produced["key"])

    session_id = db.stable_id("session:" + key)
    attempt_id = db.stable_id("attempt:" + key)
    item_id = db.stable_id("content:" + key)
    learner_id = db.stable_id("learner:" + produced["learner"])

    turns = [dict(t) for t in produced["turns"]]
    flags_by_turn = {}

    if group == "too_short":
        for turn in turns:
            if turn["role"] == "candidate":
                turn["text"] = rng.choice(SHORT_ANSWERS)
    if group == "injection":
        targets = [t for t in turns if t["role"] == "candidate"]
        hit = targets[len(targets) // 2]
        hit["text"] = hit["text"].rstrip() + " " + variant["probe"]

    low_stt = group == "low_stt_confidence"
    stt_profile = spec["stt"]["low" if low_stt else "normal"]

    started = datetime.fromisoformat(produced["started_at"])
    turn_rows, asked_rows = [], []
    clock = 0.0
    turn_no = 0
    for turn in turns:
        part = PART[int(turn["part"])]
        if turn["role"] == "examiner":
            asked_rows.append({"part": part, "text": turn["text"].strip()})
            # Lời giám khảo cũng chiếm thời gian trên đồng hồ phiên.
            clock += len(words(turn["text"])) / 2.6 + rng.uniform(0.4, 1.5)
            continue
        turn_no += 1
        duration = turn_timing(rng, turn["text"], rate, band)
        row = db.SpeakingTurn(
            id=db.stable_id(f"turn:{key}:{turn_no}"),
            attempt_id=attempt_id, turn_no=turn_no, part=part,
            transcript=turn["text"].strip(),
            stt_confidence=sample_confidence(rng, stt_profile),
            duration_s=duration, t_start_s=round(clock, 2))
        clock += duration + rng.uniform(0.2, 0.9)
        flags = []
        if len(words(turn["text"])) < 8:
            flags.append("too_short")
        if group == "injection" and variant["probe"] in turn["text"]:
            flags.append("injection_detected")
        if low_stt and row.stt_confidence < spec["stt"]["low_threshold"]:
            flags.append("low_stt_confidence")
        flags_by_turn[str(row.id)] = flags
        turn_rows.append(row.model_dump())

    points = candidate_points(turn_rows, flags_by_turn)

    # refs_point_id: câu Part 3 bám vào một ý đã nói. NULL khoảng 40% như mục 1.
    pool = [p for p in points]
    asked_out = []
    for index, asked in enumerate(asked_rows):
        ref = None
        if asked["part"] == "part3" and index and pool and rng.random() > 0.4:
            overlap = [p for p in pool
                       if set(w.lower() for w in words(p.point) if len(w) >= 5)
                       & set(w.lower() for w in words(asked["text"]) if len(w) >= 5)]
            ref = (overlap or pool)[rng.randrange(len(overlap or pool))].id
        asked_out.append(db.AskedQuestion(
            id=db.stable_id(f"asked:{key}:{index}"), attempt_id=attempt_id,
            part=asked["part"], text=asked["text"], refs_point_id=ref))

    transcript = "\n".join(
        f"{'Examiner' if t['role'] == 'examiner' else 'Candidate'}: {t['text'].strip()}"
        for t in turns)
    submitted = started + timedelta(seconds=round(clock) + rng.randint(5, 60))

    item = db.ContentItem(
        item_id=item_id, question_type="speaking_full" if not group else f"speaking_{group}",
        topic=", ".join(produced["topics"]), target_band=band,
        source="llm_generated_verified", license="CC0-1.0",
        author="synth/speaking", model=produced.get("model"),
        prompt_version=produced.get("prompt_version"), status="verified",
        # Đề cũng do LLM sinh, nên body trỏ về đúng bản ghi trong ngân hàng đề:
        # đọc một CONTENT_ITEM là truy được cả transcript lẫn đề về lệnh gọi nào.
        body={"part1_questions": produced["part1_questions"],
              "cue_card": session["cue_card"],
              "question_bank": {"schema": qbank.SCHEMA,
                                "exam_set": session.get("exam_set"),
                                "topics": produced["topics"],
                                "cue_card_id": produced["cue_card"]}},
        created_at=started)
    attempt = db.Attempt(
        attempt_id=attempt_id, session_id=session_id, item_id=item_id,
        # Transcript không có audio nên mode = text và PR sẽ là not_assessed.
        # Nhóm low_stt_confidence mô phỏng vòng TTS -> nhiễu -> Whisper, audio
        # đã xoá theo quy định 1.5.4.
        mode="voice" if low_stt else "text",
        text_or_transcript=transcript, audio_uri=None,
        audio_deleted_at=submitted + timedelta(minutes=rng.randint(1, 30))
        if low_stt else None,
        submitted_at=submitted, raw_score=None)
    session_row = db.Session(
        id=session_id, learner_id=learner_id,
        kind="mock" if not group else "practice", status="finished",
        thread_id=f"synth-{key}")

    return {
        "key": key,
        "intended_band": band,
        "split": produced.get("split"),
        "group": group,
        "base_key": (variant or {}).get("base_key"),
        "sessions": [session_row.model_dump()],
        "content_items": [item.model_dump()],
        "attempts": [attempt.model_dump()],
        "speaking_turns": turn_rows,
        "candidate_points": [p.model_dump() for p in points],
        "asked_questions": [a.model_dump() for a in asked_out],
        "flags": flags_by_turn,
    }


def build_placement(spec, one, rng):
    """Bộ Part 1 ngắn cho UC-01: attempt riêng, không có Part 2 và Part 3."""
    key = one["key"]
    attempt_id = db.stable_id("attempt:" + key)
    turn_rows, asked = [], []
    clock, turn_no = 0.0, 0
    band = one["intended_band"]
    rate = spec["band_profiles"][band]["speech_rate"]
    for turn in one["turns"]:
        if turn["role"] == "examiner":
            asked.append(turn["text"].strip())
            clock += len(words(turn["text"])) / 2.6 + rng.uniform(0.4, 1.2)
            continue
        turn_no += 1
        duration = turn_timing(rng, turn["text"], rate, band)
        turn_rows.append(db.SpeakingTurn(
            id=db.stable_id(f"turn:{key}:{turn_no}"), attempt_id=attempt_id,
            turn_no=turn_no, part="part1", transcript=turn["text"].strip(),
            stt_confidence=sample_confidence(rng, spec["stt"]["normal"]),
            duration_s=duration, t_start_s=round(clock, 2)).model_dump())
        clock += duration + rng.uniform(0.2, 0.8)
    return {"key": key, "intended_band": band, "topic": one["topic"],
            "attempt_id": attempt_id, "questions": asked,
            "speaking_turns": turn_rows}


def collect(spec, state, sessions, placement_pool, jobs_db=None):
    attempts, manifest = [], []
    produced_meta = job_meta(jobs_db) if jobs_db else {}
    for session in state["benchmark"]:
        produced = sessions.get(session["key"])
        if not produced:
            continue
        produced = {**produced,
                    "started_at": session["started_at"].isoformat(),
                    **produced_meta.get(session["key"], {})}
        rng = random.Random(planner.sub_seed(spec["seed"], "assemble", session["key"]))
        built = build_attempt(spec, session, produced, rng)
        attempts.append(built)
        manifest.append(manifest_row(spec, built, produced, "benchmark"))

    by_key = {s["key"]: s for s in state["benchmark"]}
    for variant in state["edge"]:
        produced = sessions.get(variant["base_key"])
        if not produced:
            continue
        base = by_key[variant["base_key"]]
        produced = {**produced, "started_at": base["started_at"].isoformat(),
                    **produced_meta.get(variant["base_key"], {})}
        rng = random.Random(planner.sub_seed(spec["seed"], "assemble", variant["key"]))
        built = build_attempt(spec, base, produced, rng, variant)
        attempts.append(built)
        manifest.append(manifest_row(spec, built, produced, "edge"))

    placement = []
    for one in state["placement_sets"]:
        got = placement_pool.get(one["key"])
        if not got:
            continue
        rng = random.Random(planner.sub_seed(spec["seed"], "assemble", one["key"]))
        placement.append(build_placement(spec, got, rng))
        manifest.append({
            "key": one["key"], "set": "pipeline", "kind": "placement",
            "intended_band": one["intended_band"], "is_synthetic": True,
            "seed": one["seed"], "prompt_version": produced_meta.get(
                one["key"], {}).get("prompt_version"),
            "model": produced_meta.get(one["key"], {}).get("model"),
            "persona": None, "group": None,
        })
    return attempts, placement, manifest


def manifest_row(spec, built, produced, which):
    return {
        "key": built["key"],
        "set": "benchmark" if which == "benchmark" else "edge",
        "kind": "speaking_session",
        "intended_band": built["intended_band"],   # tham số thiết kế, KHÔNG phải điểm chuẩn
        "split": built["split"],
        "group": built["group"],
        "base_key": built["base_key"],
        "learner": produced["learner"],
        "cue_card": produced["cue_card"],
        "topics": produced["topics"],
        "model": produced.get("model"),
        "prompt_version": produced.get("prompt_version"),
        "is_synthetic": True,
        "source": "llm_generated_verified",
        "seed": planner.sub_seed(spec["seed"], "assemble", built["key"]),
    }


def job_meta(path):
    """Model và prompt_version thật đã dùng, lấy từ gen_job để truy vết."""
    import sqlite3
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    out = {}
    for row in conn.execute(
            "SELECT prompt_id, prompt_version, model, input_json FROM gen_job"
            " WHERE status = 'ok'"):
        label = json.loads(row["input_json"]).get("_session") or ""
        for key in label.replace("+", "/").split("/"):
            if not key.startswith("sp-"):
                continue
            entry = out.setdefault(key, {"model": set(), "prompt_version": set()})
            entry["model"].add(row["model"])
            entry["prompt_version"].add(row["prompt_version"])
    return {k: {"model": ",".join(sorted(v["model"])),
                "prompt_version": ",".join(sorted(v["prompt_version"]))}
            for k, v in out.items()}


def export_job_log(jobs_db, target):
    """Nhật ký lệnh gọi LLM ra JSONL để git diff được.

    Mục 8.4 yêu cầu lưu raw mọi đầu ra và không ghi đè. File SQLite giữ bản
    gốc nhưng không đọc được trong code review, nên bản JSONL này là audit
    trail đi kèm repo.
    """
    import sqlite3
    conn = sqlite3.connect(jobs_db)
    conn.row_factory = sqlite3.Row
    columns = ["job_id", "prompt_id", "prompt_version", "model", "status",
               "attempts", "tokens_in", "tokens_out", "error",
               "started_at", "finished_at"]
    lines = []
    for row in conn.execute(
            f"SELECT {', '.join(columns)}, input_json, output_raw FROM gen_job"
            " ORDER BY rowid"):
        entry = {c: row[c] for c in columns}
        entry["input"] = json.loads(row["input_json"])
        entry["output_raw"] = row["output_raw"]
        lines.append(json.dumps(entry, ensure_ascii=False, sort_keys=True))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def bank_provenance():
    """Khối provenance của ngân hàng đề, trừ phần nội dung câu hỏi.

    Câu hỏi đã nằm trong CONTENT_ITEM.body nên không lặp lại ở đây.
    """
    bank = json.loads(qbank.BANK_PATH.read_text(encoding="utf-8"))
    return {key: bank[key] for key in
            ("schema", "seed", "generated_at", "source", "license", "author",
             "note", "selection_rule", "calls", "exam_sets")} | {
        "topics": len(bank["topics"]),
        "questions": sum(len(t["questions"]) for t in bank["topics"]),
        "cue_cards": len(bank["cue_cards"]),
        # EXAM/EXAM_ITEM thuộc ERD 1 của cả hệ thống; speaking/database.py chỉ
        # mô hình phần Speaking nên không có hai bảng đó. Bộ đề để nguyên ở đây.
        "part3_fallback": sum(len(s["part3_fallback_questions"])
                              for s in bank["exam_sets"]),
    }


def main():
    spec = planner.load_spec()
    state = planner.build()
    sessions = json.loads((OUT / "sessions.json").read_text(encoding="utf-8")) \
        if (OUT / "sessions.json").exists() else {}
    pool_path = OUT / "placement_pool.json"
    pool = json.loads(pool_path.read_text(encoding="utf-8")) if pool_path.exists() else {}
    jobs_db = OUT / "gen_jobs.sqlite3"

    attempts, placement, manifest = collect(
        spec, state, sessions, pool, jobs_db if jobs_db.exists() else None)

    learners = [db.Learner(id=db.stable_id("learner:" + l["key"])).model_dump()
                for l in state["learners"]]
    payload = {
        "schema_version": db.SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spec_version": spec["version"],
        "tables": {
            "LEARNER": learners,
            "SESSION": [r for a in attempts for r in a["sessions"]],
            "CONTENT_ITEM": [r for a in attempts for r in a["content_items"]],
            "ATTEMPT": [r for a in attempts for r in a["attempts"]],
            "SPEAKING_TURN": [r for a in attempts for r in a["speaking_turns"]]
                             + [r for p in placement for r in p["speaking_turns"]],
            "CANDIDATE_POINT": [r for a in attempts for r in a["candidate_points"]],
            "ASKED_QUESTION": [r for a in attempts for r in a["asked_questions"]],
        },
        "extensions": {
            "synth_manifest": manifest,
            # Chờ giáo viên chấm. Đây là nguồn band duy nhất được dùng để kết
            # luận về chất lượng AI chấm (quy định 1.5.3).
            "gold_label": [],
            "placement_pool": placement,
            "turn_flags": {a["key"]: a["flags"] for a in attempts},
            # Nguồn gốc ngân hàng đề: model, prompt_version và job_id của từng
            # lệnh gọi. Nhờ khối này R9 provenance kiểm được chỉ từ file dữ liệu.
            "question_bank": bank_provenance(),
            "notes": [
                "intended_band là tham số thiết kế, không phải điểm chuẩn.",
                "Toàn bộ chủ đề Part 1 và cue card Part 2 do LLM sinh"
                " (prompt P6q1/P6q2), không lấy từ ngân hàng viết tay trong"
                " speaking/questions.py và không từ đề thi hay sách luyện thi.",
                "ERD 2 (ASSESSMENT..FINAL_SCORE) phải do pipeline chấm thật sinh"
                " với purpose = eval, không nằm trong file này.",
                "Nhóm low_stt_confidence mô phỏng bằng phân phối; vòng TTS ->"
                " nhiễu -> Whisper thật chưa chạy vì chưa có khóa Azure.",
            ],
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "speaking_synth_dataset.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str),
                      encoding="utf-8")
    jobs_log = 0
    if jobs_db.exists():
        jobs_log = export_job_log(jobs_db, OUT / "gen_jobs.jsonl")
    counts = {k: len(v) for k, v in payload["tables"].items()}
    print(f"{target}")
    for name, n in counts.items():
        print(f"  {name:18} {n:5}")
    print(f"  synth_manifest     {len(manifest):5}")
    print(f"  placement_pool     {len(placement):5}")
    print(f"  gen_jobs.jsonl     {jobs_log:5} lệnh gọi LLM")
    return payload


if __name__ == "__main__":
    main()
