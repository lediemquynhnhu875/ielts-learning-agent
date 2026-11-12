/**
 * Client cho lượt làm Reading/Listening (docs/reading-listening-practice.md), gọi qua route trung gian.
 * Kiểu theo backend/ielts_agent/practice/models.py và `_public_exercise` trong practice/service.py.
 * `attempt_token` chỉ trả một lần lúc tạo; các lời gọi sau gửi lại trong header X-Attempt-Token.
 */
import { request } from "./client";
import type { Exercise, PublicQuestion, QuestionGroup, QuestionType } from "./types";

import type { ListeningTurns } from "./listening";

/**
 * Một lượt nói trong audio Listening, theo GET exercises/{id}/audio/timings: mốc thời gian tính bằng giây,
 * `source_*_char` là khoảng ký tự của lượt trong script (chỉ số code point theo Python, cuối không bao gồm). Không có chữ của lượt.
 */
export type AudioTurn = { start_seconds: number; end_seconds: number; source_start_char: number; source_end_char: number };

/** Audio đã kiểm chứng của bài; GET attempts/{id} chưa trả, màn làm bài tự lấy rồi gắn vào (lib/api/listening.ts). */
export type ExerciseAudio = { url: string; turns: AudioTurn[] };

/** Câu hỏi công khai: `target` chỉ còn `item_id`, `paragraph_id`; không có `excluded`. */
export type AttemptQuestion = Omit<PublicQuestion, "excluded">;

export type AttemptQuestionGroup = Omit<QuestionGroup, "questions"> & { questions: AttemptQuestion[] };

/** Bản chụp bài lúc tạo lượt: không có đáp án, bằng chứng, trace. */
export type AttemptExercise = Pick<Exercise, "id" | "title" | "text" | "skill" | "topic" | "target_band"> & {
  question_groups: AttemptQuestionGroup[];
  audio?: ExerciseAudio;
  /** Lượt người nói của script (Listening), màn làm bài gắn vào cùng `audio`. */
  speakerTurns?: ListeningTurns | null;
};

export type QuestionResult = {
  question_id: string;
  number: number;
  question_type: QuestionType;
  response: string;
  correct_answer: string;
  is_correct: boolean;
  /** Backend hiện có: correct, unanswered, word_limit_exceeded, invalid_option, invalid_classification, incorrect. */
  reason: string;
  explanation: string;
  evidence_span: string | null;
};

export type PracticeResult = {
  grading_version: string;
  raw_score: number;
  total_questions: number;
  answered_questions: number;
  wrong_count: number;
  unanswered_count: number;
  percentage: number;
  /** Bài ngắn không suy band (`band_reason = partial_practice`). */
  band: number | null;
  band_reason: string;
  questions: QuestionResult[];
};

export type AttemptView = {
  attempt_id: string;
  item_id: string;
  skill: "reading" | "listening";
  status: "in_progress" | "submitted";
  started_at: string;
  submitted_at: string | null;
  elapsed_seconds: number;
  exercise: AttemptExercise;
  /** Theo UUID câu hỏi; câu đã xoá là chuỗi rỗng. */
  answers: Record<string, string>;
  result: PracticeResult | null;
};

export type CreatedAttempt = AttemptView & { attempt_token: string };

/** UUID câu hỏi → đáp án; `null` là xoá. Tối đa 40 câu, mỗi đáp án tối đa 2000 ký tự mỗi request. */
export type AnswerMap = Record<string, string | null>;

const withToken = (token: string, json = false): HeadersInit => ({
  "x-attempt-token": token,
  ...(json ? { "content-type": "application/json" } : {}),
});

export function createAttempt(exerciseId: string, fetchImpl: typeof fetch = fetch) {
  return request<CreatedAttempt>(`/exercises/${exerciseId}/attempts`, { method: "POST" }, fetchImpl);
}

export function getAttempt(attemptId: string, token: string, fetchImpl: typeof fetch = fetch) {
  return request<AttemptView>(`/attempts/${attemptId}`, { method: "GET", headers: withToken(token) }, fetchImpl);
}

export function saveAnswers(attemptId: string, token: string, answers: AnswerMap, fetchImpl: typeof fetch = fetch) {
  return request<AttemptView>(
    `/attempts/${attemptId}/answers`,
    { method: "PATCH", headers: withToken(token, true), body: JSON.stringify({ answers }) },
    fetchImpl,
  );
}

export function submitAttempt(attemptId: string, token: string, answers: AnswerMap, fetchImpl: typeof fetch = fetch) {
  return request<AttemptView>(
    `/attempts/${attemptId}/submit`,
    { method: "POST", headers: withToken(token, true), body: JSON.stringify({ answers }) },
    fetchImpl,
  );
}
