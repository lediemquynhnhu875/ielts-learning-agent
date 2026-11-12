"""Small manually labelled rubric retrieval check; not a grading accuracy study."""

import json
from pathlib import Path
import time

from ielts_agent.agents.speaking.grading import load_descriptors
from ielts_agent.agents.speaking.rag import RubricIndex


def evaluate():
    root = Path(__file__).resolve().parents[4] / "docs" / "speaking"
    golden = json.loads((root / "examples/rag-golden.json").read_text())
    index = RubricIndex(load_descriptors())
    if not index.corpus:
        raise ValueError("Ingest official rubric first")
    configurations = []
    for method in ("bm25", "hybrid_rerank"):
        details = []
        for case in golden:
            started = time.perf_counter()
            hits = index.search(case["query"], criterion=case["criterion"], method=method, top_k=3)
            positions = [i for i, h in enumerate(hits, 1) if h.get("band") in case["bands"]]
            details.append({"id": case["id"], "expected_bands": case["bands"], "retrieved_bands": [h.get("band") for h in hits],
                            "chunk_ids": [h["chunk_id"] for h in hits], "reciprocal_rank": 1 / positions[0] if positions else 0,
                            "abstained": not hits, "latency_ms": round((time.perf_counter() - started) * 1000, 3)})
        positive = [r for r in details if r["expected_bands"]]
        negative = [r for r in details if not r["expected_bands"]]
        configurations.append({"method": method, "hit_at_3": sum(r["reciprocal_rank"] > 0 for r in positive) / len(positive),
                               "mrr_at_3": sum(r["reciprocal_rank"] for r in positive) / len(positive),
                               "no_answer_accuracy": sum(r["abstained"] for r in negative) / len(negative),
                               "mean_query_ms": sum(r["latency_ms"] for r in details) / len(details), "details": details})
    report = {"dataset_size": len(golden), "answerable": 16, "unanswerable": 4,
              "corpus_version": index.corpus[0]["version"], "source_url": index.corpus[0].get("source_url"),
              "limitations": "Developer-labelled paraphrases; not independent or a teacher scoring benchmark. Timings exclude shared index construction.",
              "configurations": configurations}
    (root / "examples/rag-evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Kiểm tra retrieval rubric", "", "20 truy vấn tự soạn: 16 có đáp án, 4 ngoài kho. Nhãn band do người triển khai gán; cần nhóm rà soát độc lập.", "",
             "| Cấu hình | Hit@3 | MRR@3 | Từ chối đúng câu không đáp án | ms/truy vấn |", "| --- | ---: | ---: | ---: | ---: |"]
    for c in configurations:
        lines.append(f"| {c['method']} | {c['hit_at_3']:.3f} | {c['mrr_at_3']:.3f} | {c['no_answer_accuracy']:.3f} | {c['mean_query_ms']:.3f} |")
    worst = next((r for r in configurations[-1]["details"] if r["expected_bands"] and r["reciprocal_rank"] < 1), None)
    lines += ["", "Index được dựng một lần, không tính vào latency truy vấn. Đây là kiểm tra tìm rubric, không đo độ chính xác chấm IELTS.", ""]
    if worst:
        lines += [f"Ca chưa tốt: `{worst['id']}`, band nhãn {worst['expected_bands']}, thứ tự kết quả {worst['retrieved_bands']}. Các mức band dùng nhiều từ giống nhau nên LSA/BM25 có thể đặt đoạn gần nghĩa lên trước đoạn đúng mức. Khi chấm giữ toàn bộ thang band để giảm ảnh hưởng này; validator yêu cầu trích descriptor của mức điểm được gán.", ""]
    for row in configurations[-1]["details"]:
        if not row["expected_bands"] and not row["abstained"]:
            case = next(q for q in golden if q["id"] == row["id"])
            lines += [f"Ca thất bại `{row['id']}`: “{case['query']}” không có đáp án trong band descriptors, nhưng hệ thống trả các band {row['retrieved_bands']}. Từ khóa grammar/accuracy trùng rubric không chứng minh có thông tin về tuyển sinh. Bộ lọc phạm vi đơn giản chưa xử lý được câu hỏi quan hệ như vậy; UI là công cụ tra đoạn, không tự tạo câu trả lời tuyển sinh. Cần relevance judge hoặc bộ phân loại no-answer được kiểm thử độc lập trước khi dùng như chatbot hỏi đáp mở.", ""]
    lines += ["Hạn chế: reranker tuyến tính cục bộ, chưa phải cross-encoder; hỗ trợ truy vấn tiếng Anh; câu hỏi ngoài kho có từ trùng rubric vẫn có thể gây false positive. Cần thêm câu hỏi ngoài kho khó và nhãn của giáo viên.", ""]
    (root / "rag-evaluation.md").write_text("\n".join(lines))
    return [{k: v for k, v in c.items() if k != "details"} for c in configurations]


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
