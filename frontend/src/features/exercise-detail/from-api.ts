import { getExercise, getExerciseAnswers, getTrace } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { Exercise, ExerciseAnswers, Trace, TraceAttempt } from "@/lib/api/types";
import type { MockQuestionGroup, ReadingListeningExercise, Verification } from "@/mock-data/reading-listening";

const passedRules = (rules: TraceAttempt["final_rules"]) =>
  !rules?.exercise_errors?.length && !Object.values(rules?.items ?? {}).some((errors) => errors.length > 0);

/** Lần sinh được chấp nhận: lần cuối có kết quả trùng lặp đạt (bank ghi `dedup` vào lần đó khi lưu). */
function acceptedAttempt(trace: Trace): TraceAttempt | undefined {
  return [...trace.attempts].reverse().find((a) => a.dedup?.passed) ?? trace.attempts.at(-1);
}

/** 5 chặng kiểm chứng của bài đã lưu, lấy từ trace (docs/uc04.md, agents/uc04/agent.py). */
function verificationFrom(trace: Trace, questionCount: number, nearestItemTitle: string | null): Verification {
  const attempt = acceptedAttempt(trace);
  const generated = attempt?.solver?.items ? Object.keys(attempt.solver.items).length : questionCount;
  return {
    safetyPassed: trace.topic_safety?.allowed !== false && attempt?.final_content_safety?.allowed !== false,
    attempts: attempt?.attempt ?? 1,
    rulesPassed: passedRules(attempt?.final_rules ?? attempt?.rules),
    solverRetained: generated - (attempt?.removed_ids?.length ?? 0),
    solverGenerated: generated,
    maxSimilarity: attempt?.dedup?.max_similarity ?? 0,
    nearestItemId: attempt?.dedup?.nearest_item_id ?? null,
    nearestItemTitle,
  };
}

/** Ghép bài, đáp án và trace của backend thành dữ liệu trang chi tiết (cùng kiểu với mock). */
export function toReadingListeningDetail(
  exercise: Exercise,
  answers: ExerciseAnswers,
  trace: Trace,
  nearestItemTitle: string | null,
): ReadingListeningExercise {
  const byId = new Map(answers.answers.map((a) => [a.question_id, a]));
  const groups = [...exercise.question_groups].sort((a, b) => a.position - b.position);
  const questionGroups: MockQuestionGroup[] = groups.map((g) => ({
    position: g.position,
    questionType: g.question_type,
    instructions: g.instructions,
    questions: g.questions
      .filter((q) => !q.excluded)
      .sort((a, b) => a.number - b.number)
      .map((q) => ({
        number: q.number,
        prompt: q.prompt,
        answer: byId.get(q.id)?.answer_key ?? "–",
        evidenceSpan: byId.get(q.id)?.evidence_span ?? null,
      })),
  }));
  const questionCount = questionGroups.reduce((n, g) => n + g.questions.length, 0);
  const meta = trace.metadata ?? {};

  return {
    id: exercise.id,
    skill: exercise.skill,
    title: exercise.title,
    topic: exercise.topic,
    targetBand: exercise.target_band,
    source: "llm_generated_verified",
    status: exercise.status,
    model: exercise.model,
    promptVersion: exercise.prompt_version,
    createdAt: exercise.created_at,
    reportCount: 0,
    text: exercise.text,
    highlightedSpan: null,
    questionKinds: [...new Set(groups.map((g) => g.question_type))],
    questionGroups,
    verification: verificationFrom(trace, questionCount, nearestItemTitle),
    metadata: {
      model: meta.model ?? exercise.model,
      promptVersion: meta.prompt_version ?? exercise.prompt_version,
      solverModel: meta.solver_model ?? "–",
      solverPromptVersion: meta.solver_prompt_version ?? "–",
      skillHash: meta.skill_hash ?? "–",
    },
  };
}

/**
 * Tải bài Reading/Listening cho trang chi tiết của quản trị: bài, đáp án, trace và tên bài gần nhất.
 * Trả `null` khi bài không tồn tại; lỗi khác (backend tắt, CSDL chưa sẵn sàng…) ném `ApiError`.
 */
export async function loadReadingListeningDetail(id: string, fetchImpl: typeof fetch): Promise<ReadingListeningExercise | null> {
  let exercise: Exercise;
  try {
    exercise = await getExercise(id, fetchImpl);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
  const [answers, trace] = await Promise.all([getExerciseAnswers(id, fetchImpl), getTrace(exercise.trace_id, fetchImpl)]);
  const nearestId = acceptedAttempt(trace)?.dedup?.nearest_item_id;
  const nearestTitle = nearestId
    ? await getExercise(nearestId, fetchImpl).then((e) => e.title, () => null)
    : null;
  return toReadingListeningDetail(exercise, answers, trace, nearestTitle);
}
