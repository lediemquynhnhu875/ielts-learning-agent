import type { AudioTurn } from "@/lib/api/attempts";
import { codePointOffsets } from "./blocks";

/** Một đoạn audio cần phát lại, tính bằng giây. */
export type AudioSegment = { start_seconds: number; end_seconds: number };

/** Lý do chấm cần nói thêm (`reason` trong practice/grading.py); đúng, sai thường và bỏ trống đã rõ từ trạng thái và đáp án. */
const REASONS: Record<string, string> = {
  word_limit_exceeded: "Câu trả lời vượt quá số từ cho phép",
  invalid_option: "Câu trả lời không phải một lựa chọn của câu này",
  invalid_classification: "Chỉ nhận TRUE, FALSE hoặc NOT GIVEN",
};

export const reasonText = (reason: string): string | null => REASONS[reason] ?? null;

export type QuestionStatus = "correct" | "wrong" | "blank";
export type QuestionFilter = "all" | QuestionStatus;
type Graded = { is_correct: boolean; reason: string };

/** Câu chưa trả lời là "bỏ trống", không tính là sai. */
export const statusOf = (q: Graded): QuestionStatus => (q.is_correct ? "correct" : q.reason === "unanswered" ? "blank" : "wrong");

export function countStatuses(questions: Graded[]): Record<QuestionFilter, number> {
  const counts = { all: questions.length, wrong: 0, blank: 0, correct: 0 };
  for (const q of questions) counts[statusOf(q)]++;
  return counts;
}

export const filterQuestions = <T extends Graded>(questions: T[], filter: QuestionFilter): T[] =>
  filter === "all" ? questions : questions.filter((q) => statusOf(q) === filter);

/** Mở màn kết quả ở các câu sai nếu có, để xem lỗi trước. */
export const defaultFilter = (counts: Record<QuestionFilter, number>): QuestionFilter => (counts.wrong > 0 ? "wrong" : "all");

/**
 * Đoạn audio chứa bằng chứng: từ đầu lượt nói đầu tiên tới cuối lượt nói cuối cùng mà bằng chứng chạm vào; `null` nếu không tìm được.
 * Bằng chứng là chuỗi trích nguyên văn từ script; khoảng ký tự của lượt (`source_*_char`) theo code point nên phải quy đổi trước khi so.
 */
export function segmentForEvidence(turns: AudioTurn[], text: string, evidence: string | null): AudioSegment | null {
  const from = evidence?.trim() ? text.indexOf(evidence) : -1;
  if (from < 0 || !evidence) return null;
  const to = from + evidence.length;
  const offsets = codePointOffsets(text);
  const hit = turns.filter((t) => t.end_seconds > t.start_seconds && offsets[t.source_start_char] < to && offsets[t.source_end_char] > from);
  if (hit.length === 0) return null;
  return { start_seconds: Math.min(...hit.map((t) => t.start_seconds)), end_seconds: Math.max(...hit.map((t) => t.end_seconds)) };
}
