import type { AnswerMap, AttemptExercise, AttemptQuestion, AttemptQuestionGroup } from "@/lib/api/attempts";

/** Nhãn backend chấm cho T/F/NG (docs/reading-listening-practice.md); không nhận T/F/NG viết tắt. */
export const CLASSIFICATIONS = ["TRUE", "FALSE", "NOT GIVEN"] as const;

/** Backend nhận tối đa 2000 ký tự mỗi đáp án. */
export const MAX_ANSWER_CHARS = 2000;

export type Choice = { value: string; text: string };

const byPosition = <T extends { position: number }>(a: T, b: T) => a.position - b.position;

/** Nhóm và câu theo đúng thứ tự backend. */
export function groupsOf(exercise: AttemptExercise): AttemptQuestionGroup[] {
  return [...exercise.question_groups].sort(byPosition).map((g) => ({ ...g, questions: [...g.questions].sort(byPosition) }));
}

/**
 * Nhóm hiển thị: gom các nhóm cùng dạng, hướng dẫn, kiểu trả lời và giới hạn từ thành một (nhóm theo thứ tự xuất hiện đầu tiên),
 * rồi đánh số lại 1..N theo thứ tự hiển thị. Backend sinh Listening xen kẽ từng dạng, mỗi câu một nhóm;
 * Reading đã gom sẵn nên giữ nguyên. `id` câu không đổi; `number` ở đây chỉ để hiển thị, không phải số câu của backend.
 */
export function groupedQuestions(exercise: AttemptExercise): AttemptQuestionGroup[] {
  const merged = new Map<string, AttemptQuestionGroup>();
  for (const group of groupsOf(exercise)) {
    const key = JSON.stringify([group.question_type, group.response_mode, group.instructions, group.response_limits]);
    // Câu không có lựa chọn riêng dùng lựa chọn của nhóm gốc, nên mang theo khi bị gom sang nhóm khác.
    const questions = group.questions.map((q) => (Object.keys(q.options ?? {}).length > 0 || !group.options ? q : { ...q, options: group.options }));
    const into = merged.get(key);
    if (into) into.questions.push(...questions);
    else merged.set(key, { ...group, questions });
  }
  let number = 0;
  return [...merged.values()].map((g) => ({ ...g, questions: g.questions.map((q) => ({ ...q, number: ++number })) }));
}

/**
 * Có hiện câu hướng dẫn của từng nhóm không. Backend tách mỗi câu trắc nghiệm thành một nhóm (gom theo bộ lựa chọn),
 * nên câu hướng dẫn lặp lại: nhóm liền trước cùng instructions và response_mode thì không hiện lại.
 */
export function instructionsShown(groups: AttemptQuestionGroup[]): boolean[] {
  return groups.map((g, i) => {
    const prev = groups[i - 1];
    return !!g.instructions && !(prev && prev.instructions === g.instructions && prev.response_mode === g.response_mode);
  });
}

export const questionIds = (exercise: AttemptExercise) => groupedQuestions(exercise).flatMap((g) => g.questions.map((q) => q.id));

/** Lựa chọn của câu: T/F/NG gửi nhãn cố định; trắc nghiệm, matching gửi nhãn (A, B, i…), lấy của câu trước rồi tới của nhóm. */
export function choicesFor(group: AttemptQuestionGroup, question: AttemptQuestion): Choice[] {
  if (group.response_mode === "classification") return CLASSIFICATIONS.map((value) => ({ value, text: value }));
  const options = Object.keys(question.options ?? {}).length > 0 ? question.options : group.options;
  return Object.entries(options ?? {}).map(([value, text]) => ({ value, text }));
}

const LIMIT = /NO MORE THAN \S+ WORDS?/i;
const TRAILING_LIMIT = /\s*Write NO MORE THAN \S+ WORDS?(?: AND\/OR A NUMBER)? from the (?:passage|text)\.?\s*$/i;

/**
 * Backend lặp câu "Write NO MORE THAN N WORDS from the passage/text." ở cuối prompt từng câu,
 * trong khi instructions của nhóm đã nêu. Chỉ ẩn trên giao diện khi nhóm đã nêu giới hạn; không sửa dữ liệu.
 */
export function stripRepeatedLimit(prompt: string, instructions: string): string {
  return LIMIT.test(instructions) ? prompt.replace(TRAILING_LIMIT, "") : prompt;
}

const blank = (value: string | undefined) => !value || !value.trim();

/** Toàn bộ đáp án để nộp; ô trống là null. */
export function toAnswerMap(ids: string[], answers: Record<string, string>): AnswerMap {
  return Object.fromEntries(ids.map((id) => [id, blank(answers[id]) ? null : answers[id]]));
}

/** Backend nhận tối đa 40 câu mỗi request (cả lưu nháp và nộp). */
export function chunkAnswers(map: AnswerMap, size = 40): AnswerMap[] {
  const entries = Object.entries(map);
  const chunks: AnswerMap[] = [];
  for (let i = 0; i < entries.length; i += size) chunks.push(Object.fromEntries(entries.slice(i, i + size)));
  return chunks;
}

export const unansweredCount = (ids: string[], answers: Record<string, string>) => ids.filter((id) => blank(answers[id])).length;
