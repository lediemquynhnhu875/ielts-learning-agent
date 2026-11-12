"""Giai đoạn 1: dựng khung cấu trúc bằng code (generate-format.docx mục 4).

Learner, persona, lịch phiên, ID và timestamp đều suy ra từ seed nên chạy lại
cho kết quả giống hệt (metric P9). LLM không quyết định gì ở bước này.
"""

import hashlib
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

import qbank   # noqa: E402

SPEC_PATH = Path(__file__).resolve().parent / "spec.yaml"


def load_spec(path=SPEC_PATH):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def sub_seed(seed, *parts):
    """Seed con theo từng bản ghi: đổi một phiên không làm lệch các phiên khác."""
    blob = ":".join([str(seed)] + [str(p) for p in parts])
    return int(hashlib.sha256(blob.encode()).hexdigest()[:12], 16)


def round_half(value):
    return round(value * 2) / 2


def learners(spec, count=200):
    """Quần thể learner theo mục 3.5. Không cần LLM."""
    out = []
    for index in range(count):
        rng = random.Random(sub_seed(spec["seed"], "learner", index))
        overall = min(8.0, max(4.0, round_half(rng.gauss(5.8, 0.7))))
        skills = {
            skill: min(9.0, max(2.5, round(overall + rng.gauss(0, 0.4), 2)))
            for skill in ("Listening", "Reading", "Writing", "Speaking")
        }
        target = rng.choices([6.0, 6.5, 7.0, 7.5], weights=[20, 30, 30, 20])[0]
        target = max(target, overall + 0.5)
        nodes = spec["taxonomy_error"]
        low, high = spec["persona"]["weaknesses_per_persona"]
        weak = rng.sample(nodes, rng.randint(low, high))
        age_low, age_high = spec["persona"]["age"]
        yr_low, yr_high = spec["persona"]["years_english"]
        out.append({
            "index": index,
            "key": f"learner-{index:03d}",
            "band_overall": overall,
            "theta": skills,
            "target_band": min(9.0, target),
            # Lệch phải: phần lớn học 4-10 giờ, ít người học 20 giờ.
            "hours_per_week": min(20, max(4, int(rng.triangular(4, 20, 7)))),
            "rest_days": rng.randint(1, 2),
            "weeks_to_exam": rng.randint(4, 24),
            "age": rng.randint(age_low, age_high),
            "years_english": rng.randint(yr_low, yr_high),
            "weaknesses": weak,
        })
    return out


def part1_block(rng, chosen, per_topic=4):
    """Chọn câu Part 1 trong các chủ đề mà bộ đề đã ấn định.

    Cấu trúc đề (chủ đề nào đi với cue card nào) cố định ở mức ngân hàng đề,
    xem qbank.compose và qbank.SELECTION_RULE. Phần đổi giữa các phiên chỉ là
    tập con câu hỏi, nên hai phiên cùng bộ đề vẫn không trùng văn bản (W4).
    """
    block = []
    for topic in chosen:
        take = min(per_topic, len(topic["questions"]))
        picked = rng.sample(range(len(topic["questions"])), take)
        for position in sorted(picked):
            block.append({
                "topic_id": topic["id"],
                "topic": topic["name"],
                "q_id": f"{topic['id']}-{position + 1}",
                "text": topic["questions"][position],
            })
    return block


def benchmark_plan(spec, population, bank=None):
    """18 phiên đủ Part 1-3: 9 band x 2. Chia 6 dev / 12 test (mục 3.3)."""
    topics, cards, exam_sets = bank or qbank.load()
    by_topic = {t["id"]: t for t in topics}
    by_card = {c["id"]: c for c in cards}
    plan = []
    per_band = spec["benchmark"]["sessions_per_band"]
    today = datetime.now(timezone.utc).replace(microsecond=0)
    start = today - timedelta(weeks=spec["timeline"]["weeks"])
    for band_no, band in enumerate(spec["bands"]):
        for repeat in range(per_band):
            index = band_no * per_band + repeat
            rng = random.Random(sub_seed(spec["seed"], "benchmark", index))
            # Learner có θ Speaking gần band thiết kế nhất, mỗi learner một lần.
            used = {item["learner"]["key"] for item in plan}
            pool = [l for l in population if l["key"] not in used]
            learner = min(pool, key=lambda l: abs(l["theta"]["Speaking"] - band))
            exam = exam_sets[index % len(exam_sets)]
            card = by_card[exam["cue_card_id"]]
            chosen = [by_topic[t] for t in exam["part1_topics"]]
            questions = part1_block(
                rng, chosen, spec["benchmark"]["part1_questions_per_topic"])
            offset = timedelta(seconds=rng.randrange(
                int((today - start).total_seconds())))
            plan.append({
                "kind": "benchmark",
                "index": index,
                "key": f"sp-bench-{index:02d}",
                "intended_band": band,
                "split": "dev" if index % 3 == 0 else "test",
                "learner": learner,
                "exam_set": exam["id"],
                "topics": chosen,
                "part1_questions": questions,
                "cue_card": card,
                "part3_questions": spec["benchmark"]["part3_questions"],
                "started_at": start + offset,
                "seed": sub_seed(spec["seed"], "benchmark", index),
            })
    return plan


def placement_plan(spec, population, bank=None):
    """Kho dùng chung cho UC-01: 9 band x 6 bộ, gom 3 bộ mỗi lệnh gọi."""
    all_topics = (bank or qbank.load())[0]
    sets = []
    per_band = spec["placement_pool"]["sets_per_band"]
    low, high = spec["placement_pool"]["questions_per_set"]
    for band_no, band in enumerate(spec["bands"]):
        for repeat in range(per_band):
            index = band_no * per_band + repeat
            rng = random.Random(sub_seed(spec["seed"], "placement", index))
            topic = all_topics[index % len(all_topics)]
            n = rng.randint(low, high)
            picked = sorted(rng.sample(range(len(topic["questions"])),
                                       min(n, len(topic["questions"]))))
            sets.append({
                "kind": "placement",
                "index": index,
                "key": f"sp-place-{index:02d}",
                "intended_band": band,
                "topic": topic["name"],
                "questions": [topic["questions"][p] for p in picked],
                "seed": sub_seed(spec["seed"], "placement", index),
            })
    batch = spec["placement_pool"]["sets_per_call"]
    return sets, [sets[i:i + batch] for i in range(0, len(sets), batch)]


def edge_plan(spec, benchmark):
    """Biến thể ghép đôi với phiên gốc (mục 3.4): gốc là nhóm đối chứng."""
    groups = spec["edge_cases"]
    probes = spec["injection_probes"]
    # Trải đều trên dải band để không dồn vào một đầu.
    ordered = sorted(benchmark, key=lambda s: (s["intended_band"], s["index"]))
    plan, cursor = [], 0
    for group, count in (("too_short", groups["too_short"]),
                         ("injection", groups["injection"]),
                         ("low_stt_confidence", groups["low_stt_confidence"])):
        step = max(1, len(ordered) // max(1, count))
        for n in range(count):
            base = ordered[(cursor + n * step) % len(ordered)]
            plan.append({
                "kind": "edge",
                "group": group,
                "index": len(plan),
                "key": f"sp-edge-{group}-{n}",
                "base_key": base["key"],
                "intended_band": base["intended_band"],
                "probe": probes[n % len(probes)] if group == "injection" else None,
                "seed": sub_seed(spec["seed"], "edge", group, n),
            })
        cursor += 1
    return plan


def build(spec=None, population_size=200, bank=None):
    spec = spec or load_spec()
    bank = bank or qbank.load()
    population = learners(spec, population_size)
    benchmark = benchmark_plan(spec, population, bank)
    placement_sets, placement_batches = placement_plan(spec, population, bank)
    return {
        "spec": spec,
        "bank": {"topics": len(bank[0]), "cue_cards": len(bank[1]),
                 "exam_sets": len(bank[2])},
        "learners": population,
        "benchmark": benchmark,
        "placement_sets": placement_sets,
        "placement_batches": placement_batches,
        "edge": edge_plan(spec, benchmark),
    }
