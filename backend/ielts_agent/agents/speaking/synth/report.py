"""Giai đoạn 7: metric tự động cho tập Speaking (mục 5.2, 5.3, 5.4).

Mọi ngưỡng là ngưỡng khởi điểm của kịch bản, hiệu chỉnh sau pilot. Báo cáo này
KHÔNG kết luận về chất lượng AI chấm: việc đó cần gold_label của giáo viên
(quy định 1.5.3). Ở đây judge P10 chỉ là bộ lọc và intended_band chỉ là tham số
thiết kế.
"""

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import plan as planner   # noqa: E402
sys.path.insert(0, str(HERE.parents[3]))
from ielts_agent.agents.speaking import database as sdb   # noqa: E402
import validate as v     # noqa: E402

OUT = HERE / "out"

# Đếm lỗi bằng rule, chỉ cho các loại chuyển di tiếng Việt dễ nhận máy móc.
# Đây là PROXY: ngưỡng W3 của kịch bản cần ERRANT hoặc LanguageTool thật.
ERROR_RULES = [
    ("ART-MISS", re.compile(
        r"\b(?:in|on|at|to|from|with|for)\s+(?:big|small|new|old|young|good|bad)?\s*"
        r"(?:university|school|hospital|office|company|city|country|house|library)\b",
        re.I)),
    ("SVA", re.compile(r"\b(?:he|she|it|this|that)\s+(?:are|were|have|do|go|like|"
                       r"want|think|need|make|take)\b", re.I)),
    ("SVA", re.compile(r"\b(?:they|we|you|people)\s+(?:is|was|has|does)\b", re.I)),
    ("COPULA", re.compile(r"\b(?:i|he|she|it|they|we|you)\s+(?:very|really|always|"
                          r"so)\s+(?:good|bad|happy|tired|busy|interesting)\b", re.I)),
    ("AUX-MISS", re.compile(r"\b(?:i|you|we|they|he|she)\s+not\s+\w+", re.I)),
    ("PLUR-MISS", re.compile(r"\b(?:many|several|a few|two|three|four|five|lots of|"
                             r"a lot of)\s+(?:\w+ly\s+)?[a-z]+(?<![s])\b")),
    ("TENSE-PAST", re.compile(r"\b(?:yesterday|last\s+(?:week|year|month|night)|"
                              r"in\s+\d{4})\b[^.!?]{0,40}?\b(?:is|go|come|see|make|"
                              r"take|have|do|say|get)\b", re.I)),
    ("GERUND", re.compile(r"\b(?:enjoy|avoid|finish|practice|practise|suggest|"
                          r"consider)\s+to\s+\w+", re.I)),
    ("PREP", re.compile(r"\b(?:depend|depends|depended)\s+(?:of|from)\b|"
                        r"\b(?:good|bad)\s+in\s+\w+ing\b|\bdiscuss\s+about\b", re.I)),
]


def error_count(text):
    return sum(len(rx.findall(text)) for _, rx in ERROR_RULES)


def candidate_text(session):
    return " ".join(t["text"] for t in session["turns"] if t["role"] == "candidate")


def features(session):
    text = candidate_text(session)
    tokens = v.words(text)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    long_words = [w for w in tokens if len(w) >= 8]
    return {
        "words": len(tokens),
        "mtld": v.mtld(tokens),
        "sentence_len": len(tokens) / max(1, len(sentences)),
        "long_word_ratio": len(long_words) / max(1, len(tokens)),
        "errors_per_100": 100 * error_count(text) / max(1, len(tokens)),
        "ttr": len({w.lower() for w in tokens}) / max(1, len(tokens)),
    }


def qwk(a, b, low=4.0, high=9.0, step=0.5):
    """Weighted kappa bậc hai trên thang band. Dùng cho intended so với judge."""
    levels = [round(low + i * step, 1)
              for i in range(int(round((high - low) / step)) + 1)]
    index = {band: i for i, band in enumerate(levels)}

    def snap(x):
        return min(levels, key=lambda b: abs(b - x))

    n = len(levels)
    observed = [[0] * n for _ in range(n)]
    for x, y in zip(a, b):
        observed[index[snap(x)]][index[snap(y)]] += 1
    total = len(a)
    rows = [sum(r) for r in observed]
    cols = [sum(observed[i][j] for i in range(n)) for j in range(n)]
    num = den = 0.0
    for i in range(n):
        for j in range(n):
            weight = ((i - j) / (n - 1)) ** 2
            num += weight * observed[i][j]
            den += weight * rows[i] * cols[j] / total
    return 1 - num / den if den else float("nan")


def qwk_ci(a, b, rounds=4000, seed=11):
    """KTC 95% của QWK. Cùng lý do như spearman_ci: n = 18 thì QWK rất động."""
    rng = random.Random(seed)
    draws = []
    for _ in range(rounds):
        index = [rng.randrange(len(a)) for _ in range(len(a))]
        left = [a[i] for i in index]
        if len(set(left)) < 2:
            continue
        value = qwk(left, [b[i] for i in index])
        if value == value:
            draws.append(value)
    if len(draws) < 100:
        return None, None
    draws.sort()
    return (round(draws[int(0.025 * len(draws))], 3),
            round(draws[int(0.975 * len(draws))], 3))


def spearman_ci(bands, values, rounds=4000, seed=7):
    """Khoảng tin cậy 95% của rho bằng bootstrap lấy mẫu có hoàn lại.

    Benchmark chỉ có 2 phiên mỗi band, nên rho điểm rất không ổn định: thiếu
    khoảng này thì một con số 0.59 và một con số 0.71 bị đọc như hai kết luận
    khác nhau, trong khi chúng nằm trong cùng một dải nhiễu.
    """
    rng = random.Random(seed)
    size = len(values)
    draws = []
    for _ in range(rounds):
        index = [rng.randrange(size) for _ in range(size)]
        picked_bands = [bands[i] for i in index]
        if len(set(picked_bands)) < 2:
            continue
        rho = v.spearman(picked_bands, [values[i] for i in index])
        if rho == rho:
            draws.append(rho)
    if len(draws) < 100:
        return None, None
    draws.sort()
    return (round(draws[int(0.025 * len(draws))], 3),
            round(draws[int(0.975 * len(draws))], 3))


def w2_monotonic(sessions):
    """W2: các đặc trưng phải đơn điệu theo band thiết kế (rho >= 0.7)."""
    bands = [s["intended_band"] for s in sessions]
    feats = [features(s) for s in sessions]
    out = {}
    for name, sign in (("mtld", 1), ("sentence_len", 1), ("long_word_ratio", 1),
                       ("errors_per_100", -1), ("words", 1)):
        values = [f[name] * sign for f in feats]
        rho = v.spearman(bands, values)
        low, high = spearman_ci(bands, values)
        out[name] = {
            "rho": round(rho, 3) if rho == rho else None,
            "ci95": [low, high],
            "pass": bool(rho == rho and rho >= 0.7),
            # Ngưỡng 0.7 nằm trong khoảng tin cậy: dữ liệu chưa đủ để kết luận
            # đạt hay không đạt, bất kể rho điểm rơi về bên nào.
            "undecided": bool(low is not None and low < 0.7 < high),
        }
    return out


def w4_diversity(sessions):
    """W4: hai phiên cùng band không được trùng 4-gram quá 3%."""
    by_band = defaultdict(list)
    for s in sessions:
        by_band[s["intended_band"]].append(s)
    worst = []
    for band, group in sorted(by_band.items()):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                overlap = v.ngram_overlap(candidate_text(group[i]),
                                          candidate_text(group[j]))
                worst.append({"band": band, "pair": [group[i]["key"], group[j]["key"]],
                              "overlap_4gram": round(overlap, 4)})
    worst.sort(key=lambda r: -r["overlap_4gram"])
    top = worst[0]["overlap_4gram"] if worst else 0.0
    return {"pairs_compared": len(worst), "max_overlap": top,
            "pass": top <= 0.03, "worst": worst[:3]}


def w5_leaks(sessions):
    hits = []
    for s in sessions:
        for turn in s["turns"]:
            problems = v._meta_errors(s["key"], turn["text"])
            hits += problems
    return {"leaks": len(hits), "pass": not hits, "sample": hits[:3]}


def w6_lengths(spec, sessions):
    rows, bad = [], 0
    for s in sessions:
        profile = spec["band_profiles"][s["intended_band"]]
        for part, key in ((1, "part1_words"), (2, "part2_words"), (3, "part3_words")):
            answers = [t["text"] for t in s["turns"]
                       if t["role"] == "candidate" and int(t["part"]) == part]
            if not answers:
                continue
            mean = sum(len(v.words(a)) for a in answers) / len(answers)
            low, high = profile[key]
            inside = low * 0.85 <= mean <= high * 1.3
            bad += not inside
            rows.append({"key": s["key"], "band": s["intended_band"],
                         "part": part, "mean_words": round(mean, 1),
                         "target": [low, high], "in_range": inside})
    inside = sum(1 for r in rows if r["in_range"])
    share = inside / max(1, len(rows))
    return {"checked": len(rows), "in_range": inside, "share": round(share, 3),
            "pass": share >= 0.8, "outliers": [r for r in rows if not r["in_range"]][:6]}


def w7_flags(dataset):
    """W7: cờ do code gắn phải khớp nhãn edge-case đã chèn."""
    manifest = {m["key"]: m for m in dataset["extensions"]["synth_manifest"]}
    flags = dataset["extensions"]["turn_flags"]
    out = {}
    for group, flag in (("too_short", "too_short"),
                        ("injection", "injection_detected"),
                        ("low_stt_confidence", "low_stt_confidence")):
        keys = [k for k, m in manifest.items() if m.get("group") == group]
        detected = [k for k in keys
                    if any(flag in f for f in flags.get(k, {}).values())]
        controls = [k for k, m in manifest.items() if m.get("set") == "benchmark"]
        false_pos = [k for k in controls
                     if any(flag in f for f in flags.get(k, {}).values())]
        out[group] = {
            "labelled": len(keys), "detected": len(detected),
            "recall": round(len(detected) / len(keys), 3) if keys else None,
            "false_positive_on_control": len(false_pos),
            "pass": bool(keys) and len(detected) == len(keys),
        }
    return out


def p_series(dataset):
    """P1, P2, P5, P8 cho phần Speaking: toàn vẹn khoá và thứ tự thời gian."""
    tables = dataset["tables"]
    attempt_ids = {a["attempt_id"] for a in tables["ATTEMPT"]}
    item_ids = {c["item_id"] for c in tables["CONTENT_ITEM"]}
    session_ids = {s["id"] for s in tables["SESSION"]}
    learner_ids = {l["id"] for l in tables["LEARNER"]}
    turn_ids = {t["id"] for t in tables["SPEAKING_TURN"]}
    point_ids = {p["id"] for p in tables["CANDIDATE_POINT"]}

    orphans = []
    orphans += [f"ATTEMPT {a['attempt_id']} -> session" for a in tables["ATTEMPT"]
                if a["session_id"] not in session_ids]
    orphans += [f"ATTEMPT {a['attempt_id']} -> item" for a in tables["ATTEMPT"]
                if a["item_id"] not in item_ids]
    orphans += [f"SESSION {s['id']} -> learner" for s in tables["SESSION"]
                if s["learner_id"] not in learner_ids]
    # Lượt của kho placement chưa có ATTEMPT tương ứng trong bảng chính.
    placement_attempts = {p["attempt_id"] for p in
                          dataset["extensions"]["placement_pool"]}
    orphans += [f"SPEAKING_TURN {t['id']} -> attempt" for t in tables["SPEAKING_TURN"]
                if t["attempt_id"] not in attempt_ids | placement_attempts]
    orphans += [f"CANDIDATE_POINT {p['id']} -> turn" for p in tables["CANDIDATE_POINT"]
                if p["turn_id"] not in turn_ids]
    orphans += [f"ASKED_QUESTION {q['id']} -> point" for q in tables["ASKED_QUESTION"]
                if q["refs_point_id"] and q["refs_point_id"] not in point_ids]

    items = {c["item_id"]: c for c in tables["CONTENT_ITEM"]}
    order = []
    for attempt in tables["ATTEMPT"]:
        created = items[attempt["item_id"]]["created_at"]
        if attempt["submitted_at"] and str(attempt["submitted_at"]) < str(created):
            order.append(f"ATTEMPT {attempt['attempt_id']} submitted trước khi tạo item")
        if attempt["audio_deleted_at"] and attempt["submitted_at"] and \
                str(attempt["audio_deleted_at"]) < str(attempt["submitted_at"]):
            order.append(f"ATTEMPT {attempt['attempt_id']} xoá audio trước khi nộp")

    turns_by_attempt = defaultdict(list)
    for turn in tables["SPEAKING_TURN"]:
        turns_by_attempt[turn["attempt_id"]].append(turn)
    clock = []
    for attempt_id, group in turns_by_attempt.items():
        group.sort(key=lambda t: t["turn_no"])
        for before, after in zip(group, group[1:]):
            if after["t_start_s"] < before["t_start_s"] + before["duration_s"]:
                clock.append(f"{attempt_id} lượt {after['turn_no']} chồng lượt trước")

    refs = [q for q in tables["ASKED_QUESTION"] if q["part"] == "part3"]
    with_ref = [q for q in refs if q["refs_point_id"]]
    null_share = 1 - len(with_ref) / max(1, len(refs))

    return {
        "P1_orphan_rows": {"count": len(orphans), "pass": not orphans,
                           "sample": orphans[:4]},
        "P2_time_order": {"problems": len(order) + len(clock), "pass": not order and not clock,
                          "sample": (order + clock)[:4]},
        "refs_point_id_null_share": round(null_share, 3),
        "turn_count": len(tables["SPEAKING_TURN"]),
        "point_count": len(tables["CANDIDATE_POINT"]),
    }


def db_key(dataset, key):
    """attempt_id của một key trong synth_manifest.

    ID là hàm thuần của key (assemble.build_attempt), nên tra lại bằng chính
    hàm đó thay vì dựa vào thứ tự hai danh sách trùng nhau.
    """
    del dataset
    return str(sdb.stable_id("attempt:" + key))


def grounding(dataset):
    """Tiêu chí nghiệm thu UC04 đo trên dữ liệu đã lắp, không chỉ trong prompt.

    Chỉ tính trên tập benchmark. Biến thể edge-case bị loại vì too_short đã thay
    hết câu trả lời bằng "Yes." nên cố ý không còn ý nào để dẫn lại, và
    language_switch đổi ngôn ngữ của chính các ý đó.
    """
    tables = dataset["tables"]
    benchmark = {db_key(dataset, m["key"]) for m in
                 dataset["extensions"]["synth_manifest"]
                 if m.get("set") == "benchmark"}
    turns = defaultdict(list)
    for t in tables["SPEAKING_TURN"]:
        turns[t["attempt_id"]].append(t)
    asked = defaultdict(list)
    for q in tables["ASKED_QUESTION"]:
        asked[q["attempt_id"]].append(q)
    total = grounded = 0
    misses = []
    for attempt_id, questions in asked.items():
        if attempt_id not in benchmark:
            continue
        part3 = [q for q in questions if q["part"] == "part3"]
        ordered = sorted(turns[attempt_id], key=lambda t: t["turn_no"])
        pool = v.content_words(" ".join(
            t["transcript"] for t in ordered if t["part"] in ("part1", "part2")))
        # "Ý từ câu trả lời trước đó" gồm cả câu trả lời Part 3 đứng trước, nên
        # pool phải lớn dần theo từng lượt chứ không chỉ gồm Part 1 và Part 2.
        p3_answers = [t["transcript"] for t in ordered if t["part"] == "part3"]
        for index, question in enumerate(part3):
            if not index:
                continue
            total += 1
            if v.content_words(question["text"]) & pool:
                grounded += 1
            else:
                misses.append(question["text"][:70])
            if index - 1 < len(p3_answers):
                pool |= v.content_words(p3_answers[index - 1])
    share = grounded / max(1, total)
    return {"part3_followups": total, "grounded": grounded,
            "share": round(share, 3), "pass": share >= 0.95, "misses": misses[:4]}


def judge_filter(spec, sessions, jobs_path):
    """Kết quả bộ lọc P10. Judge không phải chân lý, chỉ là ngưỡng rộng."""
    import sqlite3
    if not Path(jobs_path).exists():
        return {"judged": 0, "note": "chưa chạy judge"}
    conn = sqlite3.connect(jobs_path)
    conn.row_factory = sqlite3.Row
    rows = {}
    for row in conn.execute(
            "SELECT input_json, output_json, model FROM gen_job"
            " WHERE prompt_id='P10' AND status='ok'"):
        key = json.loads(row["input_json"])["_session"].split("/")[0]
        rows[key] = {**json.loads(row["output_json"]), "model": row["model"]}
    if not rows:
        return {"judged": 0, "note": "chưa chạy judge"}
    gap_limit = spec["judge_filter"]["max_band_gap"]
    min_realism = spec["judge_filter"]["min_realism"]
    kept, dropped, intended, judged = [], [], [], []
    for key, session in sessions.items():
        verdict = rows.get(key)
        if not verdict:
            continue
        gap = abs(verdict["overall"] - session["intended_band"])
        intended.append(session["intended_band"])
        judged.append(verdict["overall"])
        record = {"key": key, "intended": session["intended_band"],
                  "judge_overall": verdict["overall"], "gap": round(gap, 2),
                  "realism": verdict["realism_1_5"],
                  "criteria": verdict["criteria"],
                  "signals": verdict.get("signals", [])[:2]}
        (kept if gap <= gap_limit and verdict["realism_1_5"] >= min_realism
         else dropped).append(record)
    mae = sum(abs(a - b) for a, b in zip(intended, judged)) / max(1, len(intended))
    realism = [r["realism"] for r in kept + dropped]
    return {
        "judged": len(intended),
        "judge_model": next(iter(rows.values()))["model"],
        "kept": len(kept), "dropped": len(dropped),
        "mae_intended_vs_judge": round(mae, 3),
        "qwk_intended_vs_judge": round(qwk(intended, judged), 3)
        if len(intended) >= 3 else None,
        "qwk_ci95": list(qwk_ci(intended, judged)) if len(intended) >= 3
        else [None, None],
        "spearman": round(v.spearman(intended, judged), 3)
        if len(intended) >= 3 else None,
        "mean_realism": round(sum(realism) / max(1, len(realism)), 2),
        "rows": sorted(kept + dropped, key=lambda r: r["intended"]),
        "dropped_keys": [r["key"] for r in dropped],
    }


def r9_provenance(dataset):
    """R9: mọi CONTENT_ITEM phải điền đủ model, prompt_version, source, license.

    Kèm kiểm tra riêng cho lần sửa này: không câu hỏi nào còn trùng với ngân
    hàng viết tay trong speaking/questions.py, vì bank đó không ghi được nguồn.
    """
    from ielts_agent.agents.speaking.questions import QUESTIONS
    handwritten = {q["text"] for q in QUESTIONS.values() if "text" in q}
    items = dataset["tables"]["CONTENT_ITEM"]
    missing, leaked = [], []
    for item in items:
        for field in ("model", "prompt_version", "source", "license", "author"):
            if not item.get(field):
                missing.append(f"{item['item_id']}.{field}")
        body = item.get("body") or {}
        for question in body.get("part1_questions") or []:
            if question.get("text") in handwritten:
                leaked.append(question["text"])
        card = body.get("cue_card") or {}
        if isinstance(card, dict) and card.get("text") in handwritten:
            leaked.append(card["text"])
    bank = dataset["extensions"].get("question_bank") or {}
    calls = bank.get("calls") or []
    return {
        "content_items": len(items),
        "fields_filled": not missing,
        "missing_fields": missing[:10],
        "questions_from_the_handwritten_bank": len(leaked),
        "bank_calls_with_model_and_job_id": sum(
            1 for c in calls if c.get("model") and c.get("job_id")),
        "bank_calls": len(calls),
        "pass": not missing and not leaked and bool(calls)
               and all(c.get("model") and c.get("job_id") for c in calls),
    }


def build():
    spec = planner.load_spec()
    sessions = json.loads((OUT / "sessions.json").read_text(encoding="utf-8"))
    ordered = sorted(sessions.values(), key=lambda s: (s["intended_band"], s["key"]))
    dataset_path = OUT / "speaking_synth_dataset.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8")) \
        if dataset_path.exists() else None

    out = {
        "sessions": len(ordered),
        "bands_covered": sorted({s["intended_band"] for s in ordered}),
        "W2_monotonic_by_band": w2_monotonic(ordered),
        "W4_diversity": w4_diversity(ordered),
        "W5_meta_leak": w5_leaks(ordered),
        "W6_lengths": w6_lengths(spec, ordered),
        "judge_P10": judge_filter(spec, sessions, OUT / "gen_jobs.sqlite3"),
        "declared_gaps": [
            "Benchmark chỉ 2 phiên mỗi band (n = 18). Khoảng tin cậy bootstrap"
            " của mọi rho W2 đều chứa ngưỡng 0.7, nên W2 ở quy mô này KHÔNG"
            " quyết định được đạt hay không đạt. Cần tăng số phiên mỗi band.",
            "Chủ đề Part 1 và cue card do LLM sinh; chưa có người đã thi IELTS"
            " duyệt lại là đề có đúng độ khó Part 1/Part 2 hay không.",
            "Mật độ lỗi là proxy bằng rule, không phải ERRANT/LanguageTool, nên"
            " ngưỡng W3 của kịch bản chưa kiểm được.",
            "Thiếu danh sách tần suất từ nên dùng tỉ lệ từ dài thay cho chỉ số"
            " 'ngoài top 2.000'.",
            "Pronunciation không benchmark được: chỉ có transcript (mục 2.8).",
            "Chưa có gold_label: mọi kết luận về chất lượng AI chấm còn bỏ trống.",
        ],
    }
    if dataset:
        out["W7_edge_flags"] = w7_flags(dataset)
        out["P_series"] = p_series(dataset)
        out["UC04_part3_grounding"] = grounding(dataset)
        out["R9_provenance"] = r9_provenance(dataset)
        out["table_counts"] = {k: len(val) for k, val in dataset["tables"].items()}
    return out


def main():
    report = build()
    (OUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\nĐã ghi {OUT / 'report.json'}")


if __name__ == "__main__":
    main()
