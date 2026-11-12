"""Driver sinh dữ liệu Speaking: nạp job, chạy, resume (mục 4 giai đoạn 2-3).

    python backend/ielts_agent/agents/speaking/synth/generate.py bank        # ngân hàng đề: chủ đề + cue card
    python backend/ielts_agent/agents/speaking/synth/generate.py pilot       # 4 phiên: 4.0, 5.5, 6.5, 8.0
    python backend/ielts_agent/agents/speaking/synth/generate.py benchmark   # 18 phiên đủ Part 1-3
    python backend/ielts_agent/agents/speaking/synth/generate.py placement   # 54 bộ Part 1 ngắn cho UC-01
    python backend/ielts_agent/agents/speaking/synth/generate.py edge        # biến thể cần LLM
    python backend/ielts_agent/agents/speaking/synth/generate.py judge       # P10 lọc mẫu
    python backend/ielts_agent/agents/speaking/synth/generate.py status

Chạy lại lệnh nào cũng an toàn: job đã ok được bỏ qua, hết quota ngày thì dừng
và hôm sau chạy tiếp từ đúng chỗ dừng.

Một phiên = 4 lệnh gọi (Part 1 hai chủ đề, Part 2, Part 3) vì Groq chặn 1.000
token đầu ra mỗi phút mỗi model. Hai generator được dùng luân phiên để nhân đôi
thông lượng.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jobs            # noqa: E402
import plan as planner  # noqa: E402
import qbank           # noqa: E402
import prompts          # noqa: E402
import validate         # noqa: E402

OUT = HERE / "out"
DB_PATH = OUT / "gen_jobs.sqlite3"
SESSIONS_PATH = OUT / "sessions.json"
PILOT_BANDS = [4.0, 5.5, 6.5, 8.0]

# LLM đếm từ không chính xác và luôn viết ngắn hơn yêu cầu (pilot: khoảng 70%
# số từ đặt hàng). Xin nhiều hơn 25% rồi vẫn nghiệm thu theo khoảng band thật.
INFLATE = 1.25


def profile_text(profile):
    """Mô tả band bằng lời, không đưa con số band vào prompt (mục 2.4)."""
    return (f"fluency and coherence — {profile['fluency_en']}; "
            f"vocabulary — {profile['lexis_en']}; "
            f"grammar — {profile['grammar_en']}")


def cue_card_text(card):
    return (f"\"{card['text']} You should say: "
            + "; ".join(card["points"]) + f"; {card['explain']}\"")


def ask_range(bounds):
    low, high = bounds
    return f"{round(low * INFLATE)}-{round(high * INFLATE)}"


def common(spec, session):
    learner = session["learner"]
    profile = spec["band_profiles"][session["intended_band"]]
    err_low, err_high = profile["errors_per_100"]
    return {
        "age": learner["age"],
        "years": learner["years_english"],
        "weakness_list": ", ".join(w["en"] for w in learner["weaknesses"]),
        "speaking_profile": profile_text(profile),
        "errors_per_100": f"{err_low}-{err_high}",
    }, profile


def p6a1_payload(spec, session, topic):
    values, profile = common(spec, session)
    questions = [q["text"] for q in session["part1_questions"]
                 if q["topic_id"] == topic["id"]]
    values.update({
        "topic": topic["name"],
        "part1_script": "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions)),
        "part1_words": ask_range(profile["part1_words"]),
        "_part1_questions": questions,
        "_bounds": {"part1": profile["part1_words"]},
        "_session": f"{session['key']}/part1-{topic['id']}",
    })
    return values


def p6a2_payload(spec, session):
    values, profile = common(spec, session)
    low, high = profile["part2_words"]
    values.update({
        "cue_card": cue_card_text(session["cue_card"]),
        "part2_words": ask_range(profile["part2_words"]),
        "part2_min": low,
        "_bounds": {"part2": profile["part2_words"]},
        "_session": f"{session['key']}/part2",
    })
    return values


def p6a3_payload(spec, session, prior_answers):
    values, profile = common(spec, session)
    quoted = "\n".join(f"- \"{a.strip()}\"" for a in prior_answers)
    values.update({
        "theme": session["cue_card"]["text"],
        "prior_answers": "\n" + quoted,
        "part3_questions": session["part3_questions"],
        "part3_words": ask_range(profile["part3_words"]),
        "_bounds": {"part3": profile["part3_words"]},
        "_prior_text": " ".join(prior_answers),
        "_session": f"{session['key']}/part3",
    })
    return values


def p6a_placement_payload(spec, batch):
    low, high = spec["placement_pool"]["questions_per_set"]
    lines = []
    for n, one in enumerate(batch, 1):
        profile = spec["band_profiles"][one["intended_band"]]
        lines.append(f"set {n} (topic {one['topic']}): {profile_text(profile)}")
    return {
        "n_sets": len(batch),
        "profiles": "\n" + "\n".join(lines),
        "questions_per_set": f"{low} to {high}",
        "_questions_bounds": [low, high],
        "_keys": [one["key"] for one in batch],
        "_session": "+".join(one["key"] for one in batch),
    }


def p7_switch_payload(session, turns, ratio=(0.15, 0.30)):
    return {
        "ratio": f"{int(ratio[0] * 100)}% to {int(ratio[1] * 100)}%",
        "turns_json": json.dumps(turns, ensure_ascii=False),
        "_original_turns": turns,
        "_ratio_bounds": list(ratio),
        "_session": f"{session['key']}/switch",
    }


def transcript_of(turns):
    label = {"examiner": "Examiner", "candidate": "Candidate"}
    return "\n".join(f"{label[t['role']]}: {t['text'].strip()}" for t in turns)


class Engine:
    """Gói budget, client và danh sách model để lệnh nào cũng dùng chung."""

    def __init__(self, db, spec, log=print):
        self.db = db
        self.spec = spec
        self.log = log
        self.budget = jobs.Budget(db, spec["limits"]["tokens_per_minute"],
                                  spec["limits"]["tokens_per_day"],
                                  spec["limits"].get("output_tokens_per_minute", 1000))
        self.groq = jobs.client()
        self.generators = [spec["models"]["generator"],
                           spec["models"]["generator_fallback"]]
        self.judges = [spec["models"]["judge"], spec["models"]["judge_fallback"]]

    def one(self, prompt_id, payload, seed, models=None):
        models = models or self.generators
        jid = jobs.enqueue(self.db, prompt_id, payload, seed, models[0])
        row = self.db.execute("SELECT * FROM gen_job WHERE job_id = ?",
                              (jid,)).fetchone()
        if row["status"] == "ok":
            self.log(f"  {prompt_id} {payload.get('_session')}: đã có, bỏ qua")
            return json.loads(row["output_json"])
        self.log(f"  {prompt_id} {payload.get('_session')}")
        return jobs.run(self.db, row, self.budget, validate.check, self.groq,
                        models=models, log=self.log)


def build_session(engine, spec, session):
    """Bốn lệnh gọi cho một phiên. Thiếu bất kỳ phần nào thì bỏ cả phiên."""
    turns = []
    for topic in session["topics"]:
        data = engine.one("P6a1", p6a1_payload(spec, session, topic),
                          session["seed"])
        if not data:
            return None
        turns += [{**t, "part": 1, "topic": topic["id"]} for t in data["turns"]]

    part2 = engine.one("P6a2", p6a2_payload(spec, session), session["seed"])
    if not part2:
        return None
    card = session["cue_card"]
    turns.append({"role": "examiner", "part": 2,
                  "text": card["text"] + " You should say: "
                          + "; ".join(card["points"]) + f"; {card['explain']}"})
    turns.append({"role": "candidate", "part": 2, "text": part2["text"]})

    prior = [t["text"] for t in turns if t["role"] == "candidate"]
    part3 = engine.one("P6a3", p6a3_payload(spec, session, prior), session["seed"])
    if not part3:
        return None
    turns += [{**t, "part": 3} for t in part3["turns"]]
    return turns


def save_sessions(sessions):
    OUT.mkdir(parents=True, exist_ok=True)
    SESSIONS_PATH.write_text(
        json.dumps(sessions, ensure_ascii=False, indent=1), encoding="utf-8")


def load_sessions():
    if not SESSIONS_PATH.exists():
        return {}
    return json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))


def run_sessions(engine, spec, picked):
    store = load_sessions()
    ok = failed = 0
    for n, session in enumerate(picked, 1):
        if session["key"] in store:
            engine.log(f"[{n}/{len(picked)}] {session['key']} đã xong, bỏ qua")
            ok += 1
            continue
        engine.log(f"[{n}/{len(picked)}] {session['key']} "
                   f"band {session['intended_band']} ({session['split']})")
        try:
            turns = build_session(engine, spec, session)
        except RuntimeError as exc:
            engine.log(f"DỪNG: {exc}")
            break
        if turns:
            store[session["key"]] = {
                "key": session["key"], "intended_band": session["intended_band"],
                "split": session["split"], "learner": session["learner"]["key"],
                "cue_card": session["cue_card"]["id"],
                "topics": [t["id"] for t in session["topics"]],
                "part1_questions": session["part1_questions"],
                "turns": turns,
            }
            save_sessions(store)
            ok += 1
            engine.log("  -> phiên xong")
        else:
            failed += 1
            engine.log("  -> thiếu phần, bỏ phiên")
    return ok, failed


def cmd_bank(args, state, db):
    """Giai đoạn 0. Phải chạy trước mọi lệnh khác: cả kế hoạch phiên lẫn kho
    placement đều lấy chủ đề và cue card từ bank này."""
    spec = planner.load_spec()
    bank = qbank.build(Engine(db, spec), spec)
    if not bank:
        return 0, 1
    counts = qbank.summary()
    print(f"\nbank: {counts['topics']} chủ đề, {counts['questions']} câu Part 1,"
          f" {counts['cue_cards']} cue card -> {qbank.BANK_PATH}")
    return len(bank["calls"]), 0


def cmd_pilot(args, state, db):
    spec = state["spec"]
    picked = [s for s in state["benchmark"]
              if s["intended_band"] in PILOT_BANDS and s["index"] % 2 == 0]
    print("Pilot " + ", ".join(f"{s['key']}@{s['intended_band']}" for s in picked))
    return run_sessions(Engine(db, spec), spec, picked)


def cmd_benchmark(args, state, db):
    spec = state["spec"]
    return run_sessions(Engine(db, spec), spec, state["benchmark"])


def placement_batches(spec, sets):
    """Band cao viết dài hơn nên gom ít bộ mỗi lệnh để không vượt OTPM."""
    out, buffer = [], []
    for one in sets:
        limit = 3 if one["intended_band"] <= 5.5 else 2
        buffer.append(one)
        if len(buffer) >= limit or one["intended_band"] != buffer[0]["intended_band"]:
            out.append(buffer)
            buffer = []
    if buffer:
        out.append(buffer)
    return out


def cmd_placement(args, state, db):
    spec = state["spec"]
    engine = Engine(db, spec)
    batches = placement_batches(spec, state["placement_sets"])
    print(f"{len(state['placement_sets'])} bộ trong {len(batches)} lệnh gọi")
    ok = failed = 0
    pool = {}
    path = OUT / "placement_pool.json"
    if path.exists():
        pool = json.loads(path.read_text(encoding="utf-8"))
    for n, batch in enumerate(batches, 1):
        if all(one["key"] in pool for one in batch):
            ok += len(batch)
            continue
        print(f"[{n}/{len(batches)}] " + ", ".join(one["key"] for one in batch))
        try:
            data = engine.one("P6a_placement", p6a_placement_payload(spec, batch),
                              batch[0]["seed"])
        except RuntimeError as exc:
            print(f"DỪNG: {exc}")
            break
        if not data:
            # Lô hỏng thường vì model chạm trần token và trả thiếu bộ. Lùi về
            # gọi từng bộ một: chậm hơn nhưng không mất bộ nào.
            print("  lô hỏng, gọi lại từng bộ")
            for one in batch:
                if one["key"] in pool:
                    continue
                single = engine.one("P6a_placement",
                                    p6a_placement_payload(spec, [one]),
                                    one["seed"])
                if single:
                    store_sets(pool, [one], single)
                    ok += 1
                else:
                    failed += 1
            path.write_text(json.dumps(pool, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            continue
        store_sets(pool, batch, data)
        path.write_text(json.dumps(pool, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        ok += len(batch)
    return ok, failed


def store_sets(pool, batch, data):
    for one, produced in zip(batch, data["sets"]):
        pool[one["key"]] = {"key": one["key"],
                            "intended_band": one["intended_band"],
                            "topic": one["topic"], "turns": produced["turns"]}


def cmd_edge(args, state, db):
    spec = state["spec"]
    sessions = {s["key"]: s for s in state["benchmark"]}
    store = load_sessions()
    engine = Engine(db, spec)
    todo = [e for e in state["edge"] if e["group"] == "language_switch"]
    if not todo:
        print("Không nhóm edge-case nào cần LLM: too_short, injection và"
              " low_stt_confidence đều do code tạo ở bước assemble.")
        return 0, 0
    ok = failed = 0
    for item in todo:
        base = store.get(item["base_key"])
        if not base:
            print(f"bỏ qua {item['key']}: chưa có phiên gốc {item['base_key']}")
            continue
        data = engine.one("P7_switch",
                          p7_switch_payload(sessions[item["base_key"]], base["turns"]),
                          item["seed"])
        ok += bool(data)
        failed += not data
    return ok, failed


def cmd_judge(args, state, db):
    spec = state["spec"]
    engine = Engine(db, spec)
    store = load_sessions()
    if not store:
        print("Chưa có phiên nào; chạy pilot hoặc benchmark trước.")
        return 0, 0
    seeds = {s["key"]: s["seed"] for s in state["benchmark"]}
    ok = failed = 0
    for n, (key, session) in enumerate(sorted(store.items()), 1):
        print(f"[{n}/{len(store)}] judge {key}")
        try:
            data = engine.one("P10",
                              {"text": transcript_of(session["turns"]),
                               "_session": f"{key}/judge"},
                              seeds.get(key, 0), models=engine.judges)
        except RuntimeError as exc:
            print(f"DỪNG: {exc}")
            break
        ok += bool(data)
        failed += not data
    return ok, failed


def cmd_status(args, state, db):
    rows = db.execute(
        "SELECT prompt_id, status, COUNT(*) n, COALESCE(SUM(tokens_in),0) ti,"
        " COALESCE(SUM(tokens_out),0) to_ FROM gen_job"
        " GROUP BY prompt_id, status ORDER BY prompt_id, status").fetchall()
    if not rows:
        print("Hàng đợi trống.")
    else:
        print(f"{'prompt':16} {'status':10} {'job':>4} {'tok_in':>8} {'tok_out':>8}")
        for row in rows:
            print(f"{row['prompt_id']:16} {row['status']:10} {row['n']:4} "
                  f"{row['ti']:8} {row['to_']:8}")
    spec = state["spec"]
    budget = jobs.Budget(db, spec["limits"]["tokens_per_minute"],
                         spec["limits"]["tokens_per_day"])
    print()
    for model in dict.fromkeys(spec["models"].values()):
        r = budget.report(model)
        print(f"{model:24} {r['day']:>7}/{r['day_limit']} token hôm nay")
    store = load_sessions()
    print(f"\nphiên đã lắp đủ: {len(store)}")
    for row in db.execute(
            "SELECT prompt_id, error FROM gen_job WHERE status='failed' LIMIT 5"):
        print(f"  failed {row['prompt_id']}: {(row['error'] or '')[:110]}")
    return 0, 0


COMMANDS = {"bank": cmd_bank, "pilot": cmd_pilot, "benchmark": cmd_benchmark,
            "placement": cmd_placement, "edge": cmd_edge,
            "judge": cmd_judge, "status": cmd_status}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    state = None if args.command == "bank" else planner.build()
    db = jobs.connect(args.db)
    ok, failed = COMMANDS[args.command](args, state, db)
    if args.command != "status":
        print(f"\n{args.command}: {ok} ok, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
