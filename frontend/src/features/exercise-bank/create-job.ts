import { ApiError } from "@/lib/api/errors";
import type { Exercise, GenerateRequest } from "@/lib/api/types";
import type { ExerciseCard } from "@/mock-data/exercises";
import { questionKindLabel } from "@/mock-data/reading-listening";

/** Dữ liệu form "Tạo bài mới" (tên trường phía giao diện). */
export type CreateRequest = {
  skill: "reading" | "listening";
  topic: string;
  targetBand: number;
  questionCount: number;
  completionWordLimit: number;
};

export type CreateResult = { ok: true; card: ExerciseCard } | { ok: false; message: string; traceId: string | null };

export function toGenerateRequest(form: CreateRequest): GenerateRequest {
  return {
    skill: form.skill,
    topic: form.topic,
    target_band: form.targetBand,
    question_count: form.questionCount,
    completion_word_limit: form.completionWordLimit,
  };
}

/** Bài backend trả về (đã kiểm chứng) thành card trong Kho đề. Câu bị loại (`excluded`) không tính. */
export function exerciseToCard(exercise: Exercise): ExerciseCard {
  const groups = [...exercise.question_groups].sort((a, b) => a.position - b.position);
  const kinds = [...new Set(groups.map((g) => g.question_type))];
  const count = groups.reduce((sum, g) => sum + g.questions.filter((q) => !q.excluded).length, 0);
  return {
    id: exercise.id,
    skill: exercise.skill,
    title: exercise.title,
    status: exercise.status,
    targetBand: exercise.target_band,
    sizeLabel: `${count} câu`,
    detailLine: kinds.map((kind) => questionKindLabel[kind]).join(" · "),
    reportCount: 0,
    createdAt: exercise.created_at,
  };
}

/** Gọi POST /api/exercises; không ném lỗi, luôn trả kết quả để giao diện hiển thị. */
export async function runCreateJob(
  form: CreateRequest,
  create: (body: GenerateRequest) => Promise<Exercise>,
): Promise<CreateResult> {
  try {
    return { ok: true, card: exerciseToCard(await create(toGenerateRequest(form))) };
  } catch (error) {
    if (error instanceof ApiError) return { ok: false, message: error.message, traceId: error.traceId };
    return { ok: false, message: "Không tạo được bài. Thử lại sau.", traceId: null };
  }
}
