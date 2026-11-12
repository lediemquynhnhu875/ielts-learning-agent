import { describe, expect, it } from "vitest";
import type { WritingAssessment } from "@/lib/api/writing";
import { forDownload, formatBand, toResultView } from "./result-view";

const essay = "Cities should limit motorbikes. A worker who live far away cannot waiting.";

function row(criterion: string, band: number, start = 0, end = 6) {
  return { criterion, band, comment: `Nhận xét ${criterion}`, evidence: [{ quote: essay.slice(start, end), start_char: start, end_char: end, verified: true }], descriptor_refs: [`R-${criterion}`] };
}

function judge(bands: Record<string, number>) {
  return { criteria: Object.entries(bands).map(([c, b]) => row(c, b)) };
}

const finalResult: WritingAssessment = {
  run_id: "run_1",
  attempt_id: "att_1",
  mode: "live",
  status: "final",
  overall_band: 6.5,
  word_count: 262,
  flags: [],
  judges: { A: judge({ TR: 6.5, CC: 6.5, LR: 7.0, GRA: 6.5 }), B: judge({ TR: 6.5, CC: 6.5, LR: 6.0, GRA: 6.5 }) },
  criteria: [row("TR", 6.5), row("CC", 6.5), row("LR", 6.0, 7, 30), row("GRA", 6.5, 32, 74)],
  reconciliation: { disputed: ["LR"], reason: "Xem comment." },
  corrections: [
    { criterion: "GRA", error_code: "subject_verb", quote: "who live", suggestion: "who lives", reason: "Chủ ngữ số ít." },
    { criterion: "LR", error_code: "word_choice", quote: "limit", suggestion: "restrict", reason: "Từ trang trọng hơn." },
  ],
  limitations: [],
};

describe("formatBand", () => {
  it("hiện một chữ số thập phân với band bước 0.5", () => {
    expect(formatBand(6)).toBe("6.0");
    expect(formatBand(6.5)).toBe("6.5");
  });

  it("giữ nguyên band trung bình lẻ của backend, không tự làm tròn", () => {
    expect(formatBand(6.75)).toBe("6.75");
  });

  it("band null hiện gạch ngang, không thành số", () => {
    expect(formatBand(null)).toBe("—");
  });
});

describe("toResultView", () => {
  it("bài chấm xong: điểm tổng của backend, 4 tiêu chí theo thứ tự kèm điểm A, B", () => {
    const view = toResultView(finalResult, "task2");
    expect(view.kind).toBe("final");
    expect(view.overall).toBe(6.5);
    expect(view.criteria.map((c) => c.code)).toEqual(["TR", "CC", "LR", "GRA"]);
    expect(view.criteria[2]).toMatchObject({ code: "LR", band: 6.0, a: 7.0, b: 6.0, disputed: true, comment: "Nhận xét LR" });
    expect(view.criteria[0].disputed).toBe(false);
  });

  it("dẫn chứng mang mã tiêu chí và vị trí ký tự", () => {
    const view = toResultView(finalResult, "task2");
    expect(view.spans).toContainEqual({ criterion: "GRA", start: 32, end: 74 });
    expect(view.spans).toHaveLength(4);
  });

  it("Task 1 hiển thị TA thay cho TR", () => {
    const view = toResultView(finalResult, "task1");
    expect(view.criteria[0].code).toBe("TA");
    expect(view.spans[0].criterion).toBe("TA");
  });

  it("lỗi và gợi ý sửa có nhãn nhóm theo tiêu chí", () => {
    const view = toResultView(finalResult, "task2");
    expect(view.corrections).toEqual([
      { category: "Grammar", original: "who live", suggestion: "who lives", reason: "Chủ ngữ số ít." },
      { category: "Lexis", original: "limit", suggestion: "restrict", reason: "Từ trang trọng hơn." },
    ]);
  });

  it("điểm cần giáo viên xem là tạm tính", () => {
    const view = toResultView({ ...finalResult, status: "provisional", overall_band: 6.0 }, "task2");
    expect(view.kind).toBe("provisional");
    expect(view.overall).toBe(6.0);
  });

  it("chế độ demo không hiện số band nào", () => {
    const view = toResultView({ ...finalResult, mode: "demo", status: "demo", overall_band: null }, "task2");
    expect(view.kind).toBe("demo");
    expect(view.overall).toBeNull();
    expect(view.criteria.every((c) => c.band === null && c.a === null && c.b === null)).toBe(true);
  });

  it("chấm lỗi: giữ nguyên thông điệp failure của backend, không có điểm", () => {
    const failed: WritingAssessment = {
      run_id: "run_2",
      attempt_id: "att_2",
      mode: "live",
      status: "failed",
      overall_band: null,
      word_count: 262,
      flags: [],
      limitations: [],
      failure: "Chưa có rubric.json. Xem README để nhập rubric chính thức trước khi chấm thật.",
    };
    const view = toResultView(failed, "task2");
    expect(view.kind).toBe("failed");
    expect(view.failure).toBe("Chưa có rubric.json. Xem README để nhập rubric chính thức trước khi chấm thật.");
    expect(view.overall).toBeNull();
    expect(view.criteria.map((c) => c.band)).toEqual([null, null, null, null]);
  });

  it("cờ thiếu độ dài và chỉ dẫn lạ thành câu tiếng Việt; cờ lạ giữ nguyên", () => {
    const view = toResultView({ ...finalResult, flags: ["under_length", "injection_detected", "other_flag"] }, "task2");
    expect(view.flags).toEqual(["Bài dưới 250 từ.", "Bài có câu giống chỉ dẫn gửi người chấm.", "other_flag"]);
    expect(toResultView({ ...finalResult, flags: ["under_length"] }, "task1").flags).toEqual(["Bài dưới 150 từ."]);
  });
});

describe("toResultView · câu giới hạn khi không có gợi ý sửa", () => {
  const limitations = [
    "Điểm AI chỉ để luyện tập; chưa hiệu chỉnh với giáo viên.",
    "Không lấy được feedback hợp lệ; chưa ghi lỗi mới vào hồ sơ.",
  ];

  it("không có gợi ý sửa thì lấy nguyên văn câu giới hạn về feedback của backend", () => {
    const view = toResultView({ ...finalResult, corrections: [], limitations }, "task2");
    expect(view.correctionsNote).toBe("Không lấy được feedback hợp lệ; chưa ghi lỗi mới vào hồ sơ.");
  });

  it("có gợi ý sửa hoặc backend không nói gì về feedback thì không có câu này", () => {
    expect(toResultView({ ...finalResult, limitations }, "task2").correctionsNote).toBeNull();
    expect(toResultView({ ...finalResult, corrections: [], limitations: [limitations[0]] }, "task2").correctionsNote).toBeNull();
  });
});

describe("forDownload", () => {
  it("bỏ trace và diagnostic (người học không xem trace), giữ phần còn lại", () => {
    const withTrace = { ...finalResult, trace: [{ step: "finish" }], diagnostic: { error_type: "X" } } as typeof finalResult;
    const out = forDownload(withTrace) as Record<string, unknown>;
    expect(out).not.toHaveProperty("trace");
    expect(out).not.toHaveProperty("diagnostic");
    expect(out).toMatchObject({ run_id: "run_1", overall_band: 6.5 });
  });
});
