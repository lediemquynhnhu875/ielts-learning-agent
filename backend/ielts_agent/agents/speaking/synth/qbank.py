"""Giai đoạn 0: sinh ngân hàng đề Speaking bằng LLM.

Trước đây Part 1 và cue card Part 2 lấy từ speaking/questions.py — 15 câu hỏi và
6 cue card viết tay trong prototype, không có nguồn gốc nào ghi lại được. Vì vậy
CONTENT_ITEM.source = llm_generated_verified chỉ đúng với transcript, còn phần
câu hỏi thì không có gì chứng minh, và R9 provenance (mục 5.1) cũng không kiểm
được bằng file. Module này sinh cả hai bằng LLM rồi lưu kèm model,
prompt_version, job_id và seed, nên toàn bộ dữ liệu có một gốc duy nhất là LLM.

Ngân hàng sinh MỘT lần và không phụ thuộc band. Trong phòng thi mọi thí sinh
nhận cùng bộ đề; nếu đề đổi theo band thì band thiết kế và độ khó của đề lẫn vào
nhau, và so sánh giữa các band mất nghĩa.

Bank gồm bốn phần:
  * topics      — chủ đề Part 1 và câu hỏi của từng chủ đề (P6q1)
  * cue_cards   — thẻ đề Part 2 (P6q2)
  * part3_bank  — câu Part 3 DỰ PHÒNG theo từng cue card (P6q3)
  * exam_sets   — bộ đề hoàn chỉnh, do CODE ghép từ ba phần trên

ID, icon, thứ tự và phép ghép bộ đề do code quyết định, không lấy từ đầu ra của
model (quyết định số 1, mục 2.1). Nhờ vậy đọc lại file là dựng lại được bank y
nguyên.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jobs      # noqa: E402
import prompts   # noqa: E402

SCHEMA = "speaking-qbank-1.0"
BANK_PATH = HERE / "out" / "question_bank.json"

# Icon chỉ để giao diện hiển thị, xoay vòng theo thứ tự chủ đề.
ICONS = ["graduation-cap", "house", "headphones", "utensils", "plane",
         "briefcase", "book", "bicycle", "camera", "music"]


# Mạo từ đầu tên thẻ không phân biệt được gì: "A challenging project" cắt còn
# "a" nếu không bỏ. Bỏ luôn ở đầu chuỗi, không bỏ ở giữa.
ARTICLES = ("a", "an", "the", "my", "your")


def slug(text, used, limit=18):
    """ID ngắn, ổn định, suy ra từ tên chủ đề; trùng thì thêm hậu tố số.

    Cắt theo ranh giới từ để ID còn đọc được: "Food and cooking" -> "food-and".
    """
    parts = [w for w in re.split(r"[^a-z0-9]+", str(text).lower()) if w]
    while len(parts) > 1 and parts[0] in ARTICLES:
        parts.pop(0)
    base = ""
    for word in parts:
        nxt = f"{base}-{word}" if base else word
        if len(nxt) > limit:
            break
        base = nxt
    base = base or (parts[0][:limit] if parts else "topic")
    candidate, n = base, 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def _read(path):
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, bank):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def _skeleton(spec):
    return {
        "schema": SCHEMA,
        "seed": spec["seed"],
        "generated_at": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat(),
        # Ba trường provenance mà R9 đòi phải điền đủ.
        "source": "llm_generated_verified",
        "license": "CC0-1.0",
        "author": "synth/speaking",
        "note": "Sinh bằng LLM, không lấy từ đề thi IELTS chính thức hay sách"
                " luyện thi. Mỗi lệnh gọi ghi ở 'calls'.",
        "calls": [],
        "topics": [],
        "cue_cards": [],
        "part3_bank": {},
        "exam_sets": [],
    }


def _call_row(db, prompt_id, payload, seed, produced_keys):
    """Model và job_id thật của một lệnh gọi, đọc lại từ gen_job để truy vết."""
    jid = jobs.job_id(prompts.VERSIONS[prompt_id], payload, seed)
    row = db.execute("SELECT model, prompt_version, tokens_in, tokens_out"
                     " FROM gen_job WHERE job_id = ?", (jid,)).fetchone()
    return {
        "prompt_id": prompt_id,
        "prompt_version": prompts.VERSIONS[prompt_id],
        "job_id": jid,
        "model": row["model"] if row else None,
        "seed": seed,
        "produced": produced_keys,
    }


def build(engine, spec, path=BANK_PATH, log=print):
    """Sinh bank theo spec['question_bank']. Chạy lại chỉ bù phần còn thiếu."""
    # Nạp muộn: plan.py import qbank để đọc bank, nên import ở đầu file sẽ vòng.
    import plan as planner
    cfg = spec["question_bank"]
    bank = _read(path) or _skeleton(spec)
    # Bank sinh ở bản cũ chưa có các khoá mới; bù vào thay vì bắt sinh lại từ đầu.
    for key, empty in _skeleton(spec).items():
        bank.setdefault(key, empty)
    topic_ids = {t["id"] for t in bank["topics"]}
    card_ids = {c["id"] for c in bank["cue_cards"]}

    while len(bank["topics"]) < cfg["topics"]:
        batch = min(cfg["topics_per_call"], cfg["topics"] - len(bank["topics"]))
        avoid = [t["name"] for t in bank["topics"]]
        payload = {
            "n_topics": batch,
            "per_topic": cfg["questions_per_topic"],
            "avoid": ", ".join(avoid) if avoid else "none yet",
            "_avoid": avoid,
            "_session": f"qbank/part1-{len(bank['topics']):02d}",
        }
        seed = planner.sub_seed(spec["seed"], "qbank", "part1",
                                len(bank["topics"]))
        data = engine.one("P6q1", payload, seed)
        if not data:
            log("  không sinh được lô chủ đề; dừng để không lưu bank thiếu")
            return None
        made = []
        for topic in data["topics"]:
            tid = slug(topic["name"], topic_ids)
            bank["topics"].append({
                "id": tid,
                "name": topic["name"].strip(),
                "icon": ICONS[(len(bank["topics"])) % len(ICONS)],
                "questions": [q.strip() for q in topic["questions"]],
            })
            made.append(tid)
        bank["calls"].append(_call_row(engine.db, "P6q1", payload, seed, made))
        _write(path, bank)
        log(f"  chủ đề: {len(bank['topics'])}/{cfg['topics']}")

    while len(bank["cue_cards"]) < cfg["cue_cards"]:
        batch = min(cfg["cards_per_call"],
                    cfg["cue_cards"] - len(bank["cue_cards"]))
        avoid = [c["title"] for c in bank["cue_cards"]]
        payload = {
            "n_cards": batch,
            "avoid": ", ".join(avoid) if avoid else "none yet",
            "_avoid": avoid,
            "_session": f"qbank/part2-{len(bank['cue_cards']):02d}",
        }
        seed = planner.sub_seed(spec["seed"], "qbank", "part2",
                                len(bank["cue_cards"]))
        data = engine.one("P6q2", payload, seed)
        if not data:
            log("  không sinh được lô cue card; dừng để không lưu bank thiếu")
            return None
        made = []
        for card in data["cards"]:
            cid = "part2-" + slug(card["title"], card_ids, limit=16)
            bank["cue_cards"].append({
                "id": cid,
                "part": 2,
                "title": card["title"].strip(),
                "text": card["text"].strip(),
                "points": [p.strip() for p in card["points"]],
                "explain": card["explain"].strip(),
            })
            made.append(cid)
        bank["calls"].append(_call_row(engine.db, "P6q2", payload, seed, made))
        _write(path, bank)
        log(f"  cue card: {len(bank['cue_cards'])}/{cfg['cue_cards']}")

    if not _part3_bank(engine, spec, bank, path, log):
        return None

    bank["selection_rule"] = SELECTION_RULE
    bank["exam_sets"] = compose(spec, bank)
    _write(path, bank)
    log(f"  bộ đề hoàn chỉnh: {len(bank['exam_sets'])}")
    return bank


def card_text(card):
    return (f"{card['text']} You should say: "
            + "; ".join(card["points"]) + f"; {card['explain']}")


def _part3_bank(engine, spec, bank, path, log):
    """Một bộ câu Part 3 dự phòng cho mỗi cue card."""
    import plan as planner
    want = spec["question_bank"]["part3_fallback_per_set"]
    for index, card in enumerate(bank["cue_cards"]):
        if card["id"] in bank["part3_bank"]:
            continue
        payload = {
            "card": card_text(card),
            "n_questions": want,
            "_session": f"qbank/part3-{card['id']}",
        }
        seed = planner.sub_seed(spec["seed"], "qbank", "part3", card["id"])
        data = engine.one("P6q3", payload, seed)
        if not data:
            log(f"  không sinh được câu Part 3 cho {card['id']}")
            return False
        bank["part3_bank"][card["id"]] = [q.strip() for q in data["questions"]]
        bank["calls"].append(
            _call_row(engine.db, "P6q3", payload, seed, [card["id"]]))
        _write(path, bank)
        log(f"  Part 3 dự phòng: {len(bank['part3_bank'])}"
            f"/{len(bank['cue_cards'])}")
    return True


SELECTION_RULE = {
    "part1": "Mỗi bộ đề lấy đúng part1_topics_per_set chủ đề. Loại trước các"
             " chủ đề trùng đề tài với cue card của bộ (giao từ nội dung từ 4"
             " ký tự trở lên), rồi ưu tiên chủ đề đang được dùng ít nhất để"
             " sáu chủ đề xuất hiện đều nhau, và không lặp lại một cặp chủ đề"
             " đã dùng ở bộ khác.",
    "part2": "Mỗi cue card đúng một bộ đề, theo thứ tự trong bank.",
    "part3": "Câu Part 3 trong bộ đề là KHO DỰ PHÒNG (UC-05). Khi thi, agent"
             " sinh câu Part 3 bám câu trả lời thật của thí sinh (P6a3); kho"
             " này chỉ dùng khi không bám được ý nào, và không dùng để đo tiêu"
             " chí nghiệm thu UC-04.",
    "per_session": "Trong một phiên, chọn benchmark.part1_questions_per_topic"
                   " câu trong số questions_per_topic câu của mỗi chủ đề, theo"
                   " seed của phiên. Cấu trúc đề cố định ở mức bank, phần đổi"
                   " giữa các phiên là tập con câu hỏi.",
}


def compose(spec, bank):
    """Ghép bộ đề hoàn chỉnh bằng code. Thuần tất định từ seed và nội dung bank."""
    import random

    import plan as planner
    import validate

    cfg = spec["question_bank"]
    per_set = cfg["part1_topics_per_set"]
    rng = random.Random(planner.sub_seed(spec["seed"], "qbank", "compose"))
    used = {topic["id"]: 0 for topic in bank["topics"]}
    seen_pairs, sets = set(), []
    for index, card in enumerate(bank["cue_cards"][:cfg["exam_sets"]]):
        theme = validate.content_words(f"{card['title']} {card['text']}", 4)
        pool = [t for t in bank["topics"]
                if not (validate.content_words(t["name"], 4) & theme)]
        if len(pool) < per_set:
            pool = list(bank["topics"])
        # Ít dùng nhất trước; rng chỉ phá thế hoà, nên kết quả vẫn tất định.
        order = sorted(pool, key=lambda t: (used[t["id"]], rng.random()))
        picked = order[:per_set]
        # Thử lần lượt các ứng viên tiếp theo cho tới khi được cặp chưa dùng.
        for swap in range(per_set, len(order)):
            if tuple(sorted(t["id"] for t in picked)) not in seen_pairs:
                break
            picked = order[:per_set - 1] + [order[swap]]
        seen_pairs.add(tuple(sorted(t["id"] for t in picked)))
        for topic in picked:
            used[topic["id"]] += 1
        sets.append({
            "id": f"set-{index:02d}",
            "part1_topics": [t["id"] for t in picked],
            "cue_card_id": card["id"],
            "part3_fallback_questions": bank["part3_bank"].get(card["id"], []),
        })
    return sets


def load(path=BANK_PATH):
    """Trả (topics, cue_cards). Thiếu bank là lỗi, không âm thầm quay về bank
    viết tay trong speaking/questions.py — đó chính là thứ cần thay."""
    bank = _read(path)
    if not bank:
        raise RuntimeError(
            f"chưa có ngân hàng đề ở {path}."
            " Chạy: python backend/ielts_agent/agents/speaking/synth/generate.py bank")
    if bank.get("schema") != SCHEMA:
        raise RuntimeError(f"{path} dùng schema {bank.get('schema')!r},"
                           f" cần {SCHEMA!r}")
    if not bank["topics"] or not bank["cue_cards"]:
        raise RuntimeError(f"{path} chưa đủ chủ đề hoặc cue card")
    if not bank.get("exam_sets"):
        raise RuntimeError(f"{path} chưa có exam_sets;"
                           " chạy lại: python backend/ielts_agent/agents/speaking/synth/generate.py bank")
    return bank["topics"], bank["cue_cards"], bank["exam_sets"]


def summary(path=BANK_PATH):
    topics, cards, sets = load(path)
    return {
        "topics": len(topics),
        "questions": sum(len(t["questions"]) for t in topics),
        "cue_cards": len(cards),
        "exam_sets": len(sets),
        "part3_fallback": sum(len(s["part3_fallback_questions"]) for s in sets),
    }
