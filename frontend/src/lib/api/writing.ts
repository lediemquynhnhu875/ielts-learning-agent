/**
 * Client cho prototype Writing (`prototypes/writing/app.py`, cổng 8765), gọi qua route trung gian.
 * Route trung gian tự đặt `mode` (WRITING_MODE), nên client không gửi `mode`.
 * Hình dạng phản hồi theo hàm `assess` của prototype: luôn 200 kể cả khi chấm lỗi (`status: "failed"`),
 * chỉ 400 khi đầu vào sai (`{ error: "<câu tiếng Việt>" }`).
 */
import { request } from "./client";

export type WritingStatus = { version: string; models: Record<string, string>; rubric_ready: boolean };

export type WritingEvidence = { quote: string; start_char: number; end_char: number; verified?: boolean };

export type WritingCriterionResult = {
  /** Backend dùng TR cho cả Task 1; giao diện Task 1 hiển thị TA. */
  criterion: string;
  band: number;
  comment: string;
  evidence: WritingEvidence[];
  descriptor_refs: string[];
};

export type WritingCorrection = {
  criterion: string;
  error_code: string;
  quote: string;
  suggestion: string;
  reason: string;
  start_char?: number;
  end_char?: number;
};

export type WritingAssessment = {
  run_id: string;
  attempt_id: string;
  mode: "demo" | "live";
  /** `final`: đã chấm; `provisional`: lệch ≥ 1.5 band, cần giáo viên xem; `demo`: điểm mô phỏng; `failed`: chưa chấm được. */
  status: "final" | "provisional" | "demo" | "failed";
  overall_band: number | null;
  word_count: number;
  flags: string[];
  judges?: { A: { criteria: WritingCriterionResult[] }; B: { criteria: WritingCriterionResult[] } };
  criteria?: WritingCriterionResult[];
  reconciliation?: { disputed: string[]; reason?: string };
  feedback?: string[];
  corrections?: WritingCorrection[];
  limitations: string[];
  /** Thông điệp lỗi của backend khi `status = failed`; hiển thị nguyên văn. */
  failure?: string;
};

export function getWritingStatus(fetchImpl: typeof fetch = fetch) {
  return request<WritingStatus>("/writing/status", { method: "GET" }, fetchImpl);
}

export type AssessInput = { promptText: string; essayText: string; attemptId?: string };

export function assessWriting(input: AssessInput, fetchImpl: typeof fetch = fetch) {
  const body = { prompt_text: input.promptText, essay_text: input.essayText, ...(input.attemptId ? { attempt_id: input.attemptId } : {}) };
  return request<WritingAssessment>(
    "/writing/assess",
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) },
    fetchImpl,
  );
}
