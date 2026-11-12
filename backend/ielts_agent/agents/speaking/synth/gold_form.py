"""Phiếu chấm gold mù cho giáo viên (generate-format.docx mục 6.2).

Quy định 1.5.3 của đề tài: band chuẩn chỉ được lấy từ giáo viên hoặc người có
chứng chỉ IELTS chấm, có ghi tên người chấm và ngày chấm. intended_band không
phải điểm chuẩn, nên phiếu này phải ẩn nó đi.

Phiếu ẩn: intended_band, model, persona, trạng thái edge-case. Thứ tự bài xáo
trộn theo seed và mỗi bài mang một mã ẩn danh. Bản đồ mã -> key thật nằm ở
blind_map.json và KHÔNG đưa cho giáo viên.

    python backend/ielts_agent/agents/speaking/synth/gold_form.py            # lượt 1
    python backend/ielts_agent/agents/speaking/synth/gold_form.py --round 2  # lượt chấm lại 20%, mã khác
"""

import argparse
import csv
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import plan as planner   # noqa: E402

OUT = HERE / "out"
GOLD = OUT / "gold"

COLUMNS = ["code", "FC", "LR", "GRA", "overall", "realism_1_5",
           "could_a_learner_have_said_this", "notes",
           "rater_name", "rated_on", "round"]

HEADER = """# Phiếu chấm Speaking — lượt {round}

Thầy/cô chấm từng bài theo band descriptor của IELTS Speaking, thang 0–9 bước 0.5.

**Chấm ba tiêu chí**: FC (Fluency and Coherence), LR (Lexical Resource),
GRA (Grammatical Range and Accuracy), cùng một điểm tổng.

**Không chấm Pronunciation.** Đây là bản gỡ băng, không có file âm thanh, nên
tiêu chí này không có dữ liệu. Cột đồng hồ dưới mỗi lượt là thời lượng nói tính
được, dùng để tham khảo khi chấm FC; dữ liệu ngắt nghỉ thật không có.

Thêm hai cột:

* **realism_1_5** — bài này giống lời một người học thật đến mức nào.
  1 = chắc chắn do máy viết, 5 = không phân biệt được.
* **could_a_learner_have_said_this** — Có hoặc Không.

Xin ghi **tên người chấm** và **ngày chấm** vào file `gold_label.csv`; đề tài
bắt buộc hai trường này.

Các bài đã được xáo trộn và đổi mã, không xếp theo trình độ.

---
"""

EDGE_HEADER = """# Phiếu xác nhận nhãn bài bất thường — lượt {round}

Phiếu này KHÔNG chấm band. Mỗi bài dưới đây đã được cố ý làm bất thường theo
một trong ba kiểu, và việc của người xem là xác nhận xem điều đó có thật đúng
như vậy trên giấy hay không:

* **quá ngắn** — thí sinh trả lời cực ngắn, kiểu "Yes." hoặc "I don't know."
* **chèn chỉ dẫn lạ** — trong lời thí sinh có câu trông như lệnh cho máy, ví dụ
  yêu cầu cho điểm 9. Hệ thống phải coi đó là dữ liệu, không phải chỉ dẫn.
* **nhận dạng giọng kém** — bản gỡ băng có độ tin cậy thấp, chữ có thể sai lệch
  so với điều thí sinh thực sự nói.

Với mỗi bài xin ghi vào `gold_label.csv`:

* **notes** — bài này thuộc kiểu nào trong ba kiểu trên, và chỗ nào cho thấy thế.
* **could_a_learner_have_said_this** — Có hoặc Không.
* **realism_1_5** — mức giống lời người học thật, 1 đến 5.

Các cột FC, LR, GRA và overall để trống. Xin ghi tên người xem và ngày xem.

---
"""


def clock(seconds):
    if seconds is None:
        return "?"
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def packet(dataset, codes, which):
    manifest = {m["key"]: m for m in dataset["extensions"]["synth_manifest"]}
    turns = {}
    for turn in dataset["tables"]["SPEAKING_TURN"]:
        turns.setdefault(turn["attempt_id"], []).append(turn)
    asked = {}
    for question in dataset["tables"]["ASKED_QUESTION"]:
        asked.setdefault(question["attempt_id"], []).append(question)
    attempts = {a["attempt_id"]: a for a in dataset["tables"]["ATTEMPT"]}

    lines = [(HEADER if which[1] == "benchmark" else EDGE_HEADER)
             .format(round=which[0])]
    for code, (key, attempt_id) in codes.items():
        attempt = attempts[attempt_id]
        own = sorted(turns.get(attempt_id, []), key=lambda t: t["turn_no"])
        questions = asked.get(attempt_id, [])
        total = sum(t["duration_s"] or 0 for t in own)
        lines.append(f"\n## Bài {code}\n")
        lines.append(f"Tổng thời lượng nói: **{clock(total)}** · số lượt: {len(own)}\n")
        by_part = {}
        for turn in own:
            by_part.setdefault(turn["part"], []).append(turn)
        q_by_part = {}
        for question in questions:
            q_by_part.setdefault(question["part"], []).append(question)
        for part, label in (("part1", "Part 1"), ("part2", "Part 2"),
                            ("part3", "Part 3")):
            if part not in by_part:
                continue
            lines.append(f"\n### {label}\n")
            pairs = zip(q_by_part.get(part, []), by_part[part])
            for question, turn in pairs:
                lines.append(f"**Giám khảo:** {question['text']}\n")
                lines.append(f"**Thí sinh** _({clock(turn['duration_s'])})_: "
                             f"{turn['transcript']}\n")
            extra = by_part[part][len(q_by_part.get(part, [])):]
            for turn in extra:
                lines.append(f"**Thí sinh** _({clock(turn['duration_s'])})_: "
                             f"{turn['transcript']}\n")
        lines.append(f"\n_Ghi kết quả cho bài {code} vào gold_label.csv._\n\n---")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, default=1,
                        help="1 = chấm lần đầu, 2 = chấm lại 20% sau >= 7 ngày")
    parser.add_argument("--resample", type=float, default=0.2)
    parser.add_argument("--set", choices=("benchmark", "edge"), default="benchmark",
                        help="benchmark = phiếu giáo viên chấm gold;"
                             " edge = phiếu người đã từng thi xác nhận nhãn")
    args = parser.parse_args(argv)

    spec = planner.load_spec()
    dataset = json.loads((OUT / "speaking_synth_dataset.json").read_text(
        encoding="utf-8"))
    manifest = dataset["extensions"]["synth_manifest"]
    rows = [m for m in manifest if m["kind"] == "speaking_session"
            and m["set"] == args.set]
    if not rows:
        raise SystemExit(f"không có bài nào thuộc tập {args.set}")

    if args.round == 2:
        # Chấm lại phân tầng theo band để intra-rater QWK không lệch về một đầu.
        # Mỗi band chỉ có 2 bài, nên sàn "ít nhất 1 bài mỗi band" sẽ đẩy tỉ lệ
        # lên 50%. Thay vào đó rút đủ số bài theo tỉ lệ rồi rải đều qua các
        # band theo thứ tự xáo trộn, mỗi band nhiều nhất 1 bài trước khi quay
        # lại vòng hai.
        rng = random.Random(planner.sub_seed(spec["seed"], "gold-resample"))
        target = max(1, round(len(rows) * args.resample))
        by_band = {}
        for row in rows:
            by_band.setdefault(row["intended_band"], []).append(row)
        for group in by_band.values():
            rng.shuffle(group)
        bands = sorted(by_band)
        rng.shuffle(bands)
        picked, depth = [], 0
        while len(picked) < target and depth < max(len(g) for g in by_band.values()):
            for band in bands:
                if len(picked) >= target:
                    break
                if depth < len(by_band[band]):
                    picked.append(by_band[band][depth])
            depth += 1
        rows = picked

    # Mã ẩn danh đổi theo lượt, nên lượt 2 giáo viên không nhận ra bài cũ.
    rng = random.Random(planner.sub_seed(spec["seed"], "gold", args.round))
    rng.shuffle(rows)
    import importlib
    sys.path.insert(0, str(HERE.parents[3]))
    sdb = importlib.import_module("ielts_agent.agents.speaking.database")
    codes = {}
    for index, row in enumerate(rows, 1):
        prefix = "R" if args.set == "benchmark" else "E"
        code = f"{prefix}{args.round}-{index:03d}"
        codes[code] = (row["key"], str(sdb.stable_id("attempt:" + row["key"])))

    GOLD.mkdir(parents=True, exist_ok=True)
    (GOLD / f"packet-{args.set}-round{args.round}.md").write_text(
        packet(dataset, codes, (args.round, args.set)), encoding="utf-8")
    with (GOLD / f"gold_label-{args.set}-round{args.round}.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for code in codes:
            writer.writerow([code] + [""] * 8 + ["", args.round])
    (GOLD / f"blind_map-{args.set}-round{args.round}.json").write_text(
        json.dumps({c: k for c, (k, _) in codes.items()}, indent=1),
        encoding="utf-8")

    print(f"{len(codes)} bài trong phiếu {args.set}, lượt {args.round}")
    who = "giáo viên" if args.set == "benchmark" else "người đã từng thi"
    print(f"  {GOLD / f'packet-{args.set}-round{args.round}.md'}      -> gửi {who}")
    print(f"  {GOLD / f'gold_label-{args.set}-round{args.round}.csv'} -> {who} điền")
    print(f"  {GOLD / f'blind_map-{args.set}-round{args.round}.json'} -> KHÔNG gửi, giữ lại để ghép")


if __name__ == "__main__":
    main()
