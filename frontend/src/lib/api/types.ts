/**
 * Kiểu dữ liệu của API UC-04, theo docs/uc04.md và backend/ielts_agent/infrastructure/db/bank.py.
 * Giữ nguyên tên trường snake_case của backend; ánh xạ sang dữ liệu giao diện làm ở tầng feature.
 */

export type QuestionType = "true_false_not_given" | "multiple_choice" | "sentence_completion" | "matching_headings";

/** Body của POST /api/exercises (GenerateRequest). */
export type GenerateRequest = {
  skill: "reading" | "listening";
  topic: string;
  target_band: number;
  question_count: number;
  completion_word_limit: number;
};

export type PublicQuestion = {
  id: string;
  position: number;
  number: number;
  prompt: string;
  options: Record<string, string>;
  target: Record<string, unknown>;
  excluded: boolean;
};

export type QuestionGroup = {
  group_id: string;
  position: number;
  question_type: QuestionType;
  instructions: string;
  response_mode: "text" | "options" | "classification";
  options: Record<string, string>;
  response_limits: Record<string, unknown>;
  allow_reuse: boolean;
  questions: PublicQuestion[];
};

/** Một bài trong GET /api/exercises: bản tóm tắt, không có nội dung bài, câu hỏi hay đáp án. Chỉ bài đã kiểm chứng. */
export type ExerciseSummary = {
  id: string;
  title: string;
  skill: "reading" | "listening";
  topic: string;
  target_band: number;
  source: string;
  status: "verified";
  created_at: string;
  question_count: number;
  /** Các dạng câu của bài, không lặp, sắp theo tên. */
  question_types: QuestionType[];
};

/** Phản hồi của GET /api/exercises (docs/uc04.md). `total` đếm mọi bài khớp bộ lọc, trước phân trang. */
export type ExerciseList = { items: ExerciseSummary[]; total: number; limit: number; offset: number };

/** Query của GET /api/exercises. `q` tìm trong tiêu đề và chủ đề; `limit` 1–100. */
export type ExerciseListParams = { skill?: "reading" | "listening"; q?: string; limit: number; offset: number };

/** Phản hồi của POST /api/exercises (201) và GET /api/exercises/{id}. Không chứa đáp án. */
export type Exercise = {
  id: string;
  title: string;
  text: string;
  skill: "reading" | "listening";
  topic: string;
  target_band: number;
  source: string;
  status: "verified" | "spare" | "rejected";
  model: string;
  prompt_version: string;
  position: number;
  created_at: string;
  trace_id: string;
  validation: { rules: boolean; solver: boolean };
  question_groups: QuestionGroup[];
};

/** Phản hồi của GET /api/exercises/{id}/answers. */
export type ExerciseAnswers = {
  item_id: string;
  answers: {
    question_id: string;
    number: number;
    answer_key: string;
    evidence_span: string | null;
    explanation: string;
  }[];
};

export type DedupResult = {
  passed: boolean;
  metric?: string;
  threshold?: number;
  max_similarity?: number;
  nearest_item_id?: string | null;
  similarity?: number;
  matched_item_id?: string;
};

export type TraceAttempt = {
  attempt: number;
  reason?: string;
  rules?: { status?: string; exercise_errors?: string[]; items?: Record<string, string[]> };
  solver?: { status?: string; items?: Record<string, { passed: boolean }>; protocol_errors?: string[] };
  /** Kiểm quy tắc lại trên các câu còn giữ sau solver. */
  final_rules?: { exercise_errors?: string[]; items?: Record<string, string[]> };
  removed_ids?: string[];
  removed_ratio?: number;
  content_safety?: { allowed: boolean };
  final_content_safety?: { allowed: boolean };
  dedup?: DedupResult;
};

/** Phản hồi của GET /api/traces/{trace_id}: kết quả an toàn, các lần sinh, kiểm chứng và trùng lặp. */
export type Trace = {
  id: string;
  status: string;
  item_id?: string;
  request?: GenerateRequest;
  metadata?: {
    model?: string;
    prompt_version?: string;
    solver_model?: string;
    solver_prompt_version?: string;
    skill_hash?: string;
  };
  topic_safety?: { allowed: boolean };
  attempts: TraceAttempt[];
};
