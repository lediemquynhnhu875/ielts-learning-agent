import { describe, expect, it } from "vitest";
import type { Exercise, ExerciseAnswers, Trace } from "@/lib/api/types";
import { loadReadingListeningDetail, toReadingListeningDetail } from "./from-api";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";
const TRACE = "0e9d8c7b-6a5f-4e3d-8c2b-1a0f9e8d7c6b";
const NEAREST = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d";

const q = (id: string, number: number) => ({ id, position: number, number, prompt: `Q${number}`, options: {}, target: {}, excluded: false });

const exercise: Exercise = {
  id: ID,
  title: "Life on the Water",
  text: "[A]\nOne.\n\n[B]\nTwo.",
  skill: "reading",
  topic: "Floating markets",
  target_band: 6.5,
  source: "llm_generated_verified",
  status: "verified",
  model: "deepseek-chat",
  prompt_version: "reading-item-generation-v3",
  position: 1,
  created_at: "2026-10-29T13:00:00Z",
  trace_id: TRACE,
  validation: { rules: true, solver: true },
  question_groups: [
    { group_id: "g2", position: 2, question_type: "multiple_choice", instructions: "Choose A, B or C.", response_mode: "options", options: {}, response_limits: {}, allow_reuse: false, questions: [q("q3", 3)] },
    { group_id: "g1", position: 1, question_type: "true_false_not_given", instructions: "TRUE/FALSE/NOT GIVEN", response_mode: "classification", options: {}, response_limits: {}, allow_reuse: false, questions: [q("q1", 1), q("q2", 2)] },
  ],
};

const answers: ExerciseAnswers = {
  item_id: ID,
  answers: [
    { question_id: "q1", number: 1, answer_key: "TRUE", evidence_span: "One.", explanation: "" },
    { question_id: "q2", number: 2, answer_key: "NOT GIVEN", evidence_span: null, explanation: "" },
    { question_id: "q3", number: 3, answer_key: "B", evidence_span: "Two.", explanation: "" },
  ],
};

const trace: Trace = {
  id: TRACE,
  status: "verified",
  item_id: ID,
  metadata: { model: "deepseek-chat", prompt_version: "reading-item-generation-v3", solver_model: "deepseek-reasoner", solver_prompt_version: "blind-solver-v2", skill_hash: "9f2c41ab77" },
  topic_safety: { allowed: true },
  attempts: [
    { attempt: 1, reason: "exercise_rule_failure", rules: { exercise_errors: ["too short"], items: {} } },
    {
      attempt: 2,
      rules: { exercise_errors: [], items: {} },
      solver: { items: { a: { passed: true }, b: { passed: true }, c: { passed: false }, d: { passed: true } } },
      removed_ids: ["c"],
      final_rules: { exercise_errors: [], items: { a: [], b: [], d: [] } },
      final_content_safety: { allowed: true },
      dedup: { passed: true, threshold: 0.9, max_similarity: 0.41, nearest_item_id: NEAREST },
    },
  ],
};

describe("toReadingListeningDetail", () => {
  const detail = toReadingListeningDetail(exercise, answers, trace, "Floating Markets of the Mekong");

  it("giữ thông tin bài và sắp nhóm câu theo position, ghép đáp án theo question_id", () => {
    expect(detail).toMatchObject({ id: ID, skill: "reading", title: "Life on the Water", targetBand: 6.5, status: "verified", reportCount: 0 });
    expect(detail.questionKinds).toEqual(["true_false_not_given", "multiple_choice"]);
    expect(detail.questionGroups.map((g) => g.questions.map((x) => [x.number, x.answer, x.evidenceSpan]))).toEqual([
      [[1, "TRUE", "One."], [2, "NOT GIVEN", null]],
      [[3, "B", "Two."]],
    ]);
  });

  it("lấy 5 chặng kiểm chứng từ lần sinh được chấp nhận trong trace", () => {
    expect(detail.verification).toEqual({
      safetyPassed: true,
      attempts: 2,
      rulesPassed: true,
      solverRetained: 3,
      solverGenerated: 4,
      maxSimilarity: 0.41,
      nearestItemId: NEAREST,
      nearestItemTitle: "Floating Markets of the Mekong",
    });
    expect(detail.metadata).toEqual({
      model: "deepseek-chat",
      promptVersion: "reading-item-generation-v3",
      solverModel: "deepseek-reasoner",
      solverPromptVersion: "blind-solver-v2",
      skillHash: "9f2c41ab77",
    });
  });
});

/** Backend giả trả theo đường dẫn; ghi lại các đường dẫn đã gọi. */
function fakeApi(routes: Record<string, [number, unknown]>) {
  const calls: string[] = [];
  const impl = (async (url: string | URL | Request) => {
    const path = String(url);
    calls.push(path);
    const [status, body] = routes[path] ?? [404, { detail: "Not found" }];
    return new Response(JSON.stringify(body), { status });
  }) as typeof fetch;
  return { calls, impl };
}

describe("loadReadingListeningDetail", () => {
  it("trả null khi backend báo không tìm thấy bài", async () => {
    const api = fakeApi({});
    expect(await loadReadingListeningDetail(ID, api.impl)).toBeNull();
    expect(api.calls).toEqual([`/api/backend/exercises/${ID}`]);
  });

  it("gọi bài, đáp án, trace và tên bài gần nhất rồi ghép lại", async () => {
    const api = fakeApi({
      [`/api/backend/exercises/${ID}`]: [200, exercise],
      [`/api/backend/exercises/${ID}/answers`]: [200, answers],
      [`/api/backend/traces/${TRACE}`]: [200, trace],
      [`/api/backend/exercises/${NEAREST}`]: [200, { ...exercise, id: NEAREST, title: "Nearest one" }],
    });
    const detail = await loadReadingListeningDetail(ID, api.impl);
    expect(detail?.verification.nearestItemTitle).toBe("Nearest one");
    expect(detail?.questionGroups[0].questions[0].answer).toBe("TRUE");
  });

  it("vẫn hiện bài khi không lấy được tên bài gần nhất", async () => {
    const api = fakeApi({
      [`/api/backend/exercises/${ID}`]: [200, exercise],
      [`/api/backend/exercises/${ID}/answers`]: [200, answers],
      [`/api/backend/traces/${TRACE}`]: [200, trace],
    });
    const detail = await loadReadingListeningDetail(ID, api.impl);
    expect(detail?.verification.nearestItemTitle).toBeNull();
  });

  it("ném lỗi (không trả null) khi backend lỗi khác 404", async () => {
    const api = fakeApi({ [`/api/backend/exercises/${ID}`]: [503, { error: "database_unavailable", message: "PostgreSQL chưa sẵn sàng." }] });
    await expect(loadReadingListeningDetail(ID, api.impl)).rejects.toMatchObject({ status: 503 });
  });
});
