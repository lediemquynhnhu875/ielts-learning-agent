import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import type { Exercise, GenerateRequest } from "@/lib/api/types";
import { exerciseToCard, runCreateJob, toGenerateRequest, type CreateRequest } from "./create-job";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";
const TRACE = "0e9d8c7b-6a5f-4e3d-8c2b-1a0f9e8d7c6b";

const form: CreateRequest = { skill: "listening", topic: "Floating markets", targetBand: 6.5, questionCount: 10, completionWordLimit: 2 };

function question(n: number, excluded = false) {
  return { id: `q${n}`, position: n, number: n, prompt: "?", options: {}, target: {}, excluded };
}

const exercise: Exercise = {
  id: ID,
  title: "Life on the Water",
  text: "…",
  skill: "listening",
  topic: "Floating markets",
  target_band: 6.5,
  source: "llm_generated_verified",
  status: "verified",
  model: "deepseek-chat",
  prompt_version: "v3",
  position: 1,
  created_at: "2026-10-29T13:00:00Z",
  trace_id: TRACE,
  validation: { rules: true, solver: true },
  question_groups: [
    { group_id: "g1", position: 1, question_type: "sentence_completion", instructions: "", response_mode: "text", options: {}, response_limits: {}, allow_reuse: false, questions: [question(1), question(2, true), question(3)] },
    { group_id: "g2", position: 2, question_type: "multiple_choice", instructions: "", response_mode: "options", options: {}, response_limits: {}, allow_reuse: false, questions: [question(4), question(5)] },
    { group_id: "g3", position: 3, question_type: "sentence_completion", instructions: "", response_mode: "text", options: {}, response_limits: {}, allow_reuse: false, questions: [question(6)] },
  ],
};

describe("toGenerateRequest", () => {
  it("đổi dữ liệu form sang body GenerateRequest đúng tên trường backend", () => {
    expect(toGenerateRequest(form)).toEqual({
      skill: "listening",
      topic: "Floating markets",
      target_band: 6.5,
      question_count: 10,
      completion_word_limit: 2,
    });
  });
});

describe("exerciseToCard", () => {
  it("chỉ đếm câu không bị loại và liệt kê dạng câu theo thứ tự, không lặp", () => {
    expect(exerciseToCard(exercise)).toEqual({
      id: ID,
      skill: "listening",
      title: "Life on the Water",
      status: "verified",
      targetBand: 6.5,
      sizeLabel: "5 câu",
      detailLine: "Fill · MCQ",
      reportCount: 0,
      createdAt: "2026-10-29T13:00:00Z",
    });
  });
});

describe("runCreateJob", () => {
  it("gửi body đã đổi tên trường và trả card khi tạo thành công", async () => {
    const sent: GenerateRequest[] = [];
    const result = await runCreateJob(form, async (body) => {
      sent.push(body);
      return exercise;
    });
    expect(sent).toEqual([toGenerateRequest(form)]);
    expect(result).toEqual({ ok: true, card: exerciseToCard(exercise) });
  });

  it("trả thông báo và mã trace khi backend báo lỗi", async () => {
    const result = await runCreateJob(form, async () => {
      throw new ApiError("Chủ đề không phù hợp; hãy chọn một chủ đề học thuật khác.", 400, "unsafe_topic", TRACE);
    });
    expect(result).toEqual({ ok: false, message: "Chủ đề không phù hợp; hãy chọn một chủ đề học thuật khác.", traceId: TRACE });
  });

  it("trả thông báo chung khi gặp lỗi không phải ApiError", async () => {
    const result = await runCreateJob(form, async () => {
      throw new Error("boom");
    });
    expect(result).toEqual({ ok: false, message: "Không tạo được bài. Thử lại sau.", traceId: null });
  });
});
