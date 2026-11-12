import type { WritingAssessment, WritingCriterionResult } from "@/lib/api/writing";
import type { WritingTask } from "@/mock-data/writing";
import type { EvidenceSpan } from "./evidence";

export type ResultKind = WritingAssessment["status"];

export type CriterionView = {
  /** Mã hiển thị: TA (Task 1) hoặc TR (Task 2), CC, LR, GRA. */
  code: string;
  band: number | null;
  a: number | null;
  b: number | null;
  /** Hai giám khảo lệch ≥ 1.0 band ở tiêu chí này, điểm do bước đối chiếu quyết định. */
  disputed: boolean;
  comment: string | null;
};

export type CorrectionView = { category: string; original: string; suggestion: string; reason: string };

export type ResultView = {
  kind: ResultKind;
  overall: number | null;
  criteria: CriterionView[];
  spans: EvidenceSpan[];
  corrections: CorrectionView[];
  flags: string[];
  failure: string | null;
  /** Không có gợi ý sửa: câu giới hạn của backend giải thích lý do (nguyên văn), nếu có. */
  correctionsNote: string | null;
};

const ORDER = ["TR", "CC", "LR", "GRA"] as const;

const category: Record<string, string> = { TR: "Task", CC: "Cohesion", LR: "Lexis", GRA: "Grammar" };

const minWords: Record<WritingTask, number> = { task1: 150, task2: 250 };

/** Band bước 0.5 hiện một chữ số thập phân; band trung bình lẻ của backend (6.75) giữ nguyên; null là "—". */
export function formatBand(band: number | null): string {
  if (band === null) return "—";
  return Number.isInteger(band * 2) ? band.toFixed(1) : String(band);
}

const byCode = (rows: WritingCriterionResult[] | undefined) => new Map((rows ?? []).map((r) => [r.criterion, r]));

/**
 * Đổi kết quả chấm của backend thành dữ liệu hiển thị. Không tự tính band nào ở client:
 * điểm tổng và điểm từng tiêu chí lấy nguyên từ backend; demo và chấm lỗi không có số.
 */
export function toResultView(result: WritingAssessment, task: WritingTask): ResultView {
  const showBands = result.status === "final" || result.status === "provisional";
  const rows = byCode(result.criteria);
  const judgeA = byCode(result.judges?.A.criteria);
  const judgeB = byCode(result.judges?.B.criteria);
  const disputed = new Set(result.reconciliation?.disputed ?? []);
  const display = (code: string) => (code === "TR" && task === "task1" ? "TA" : code);
  const band = (row: WritingCriterionResult | undefined) => (showBands && row ? row.band : null);

  const criteria = ORDER.map((code) => ({
    code: display(code),
    band: band(rows.get(code)),
    a: band(judgeA.get(code)),
    b: band(judgeB.get(code)),
    disputed: disputed.has(code),
    comment: rows.get(code)?.comment ?? null,
  }));

  const spans = result.status === "failed" ? [] : ORDER.flatMap((code) =>
    (rows.get(code)?.evidence ?? []).map((ev) => ({ criterion: display(code), start: ev.start_char, end: ev.end_char })),
  );

  const corrections = (result.corrections ?? []).map((c) => ({
    category: category[c.criterion] ?? c.criterion,
    original: c.quote,
    suggestion: c.suggestion,
    reason: c.reason,
  }));

  const flags = result.flags.map((flag) => {
    if (flag === "under_length") return `Bài dưới ${minWords[task]} từ.`;
    if (flag === "injection_detected") return "Bài có câu giống chỉ dẫn gửi người chấm.";
    return flag;
  });

  return {
    kind: result.status,
    overall: showBands ? result.overall_band : null,
    criteria,
    spans,
    corrections,
    flags,
    failure: result.status === "failed" ? (result.failure ?? "Chưa chấm được.") : null,
    correctionsNote: corrections.length === 0 ? (result.limitations.find((l) => /feedback/i.test(l)) ?? null) : null,
  };
}

/** Bản tải JSON cho người học: bỏ trace và diagnostic (người học không xem trace). */
export function forDownload(result: WritingAssessment): Omit<WritingAssessment, "trace" | "diagnostic"> {
  const copy: Record<string, unknown> = { ...result };
  delete copy.trace;
  delete copy.diagnostic;
  return copy as Omit<WritingAssessment, "trace" | "diagnostic">;
}
