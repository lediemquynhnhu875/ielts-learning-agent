import { describe, expect, it } from "vitest";
import { assessWriting, getWritingStatus } from "./writing";

type Call = { url: string; init?: RequestInit };

function fakeFetch(status: number, body: unknown) {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  return { calls, fetchImpl };
}

describe("getWritingStatus", () => {
  it("gọi GET writing/status qua route trung gian", async () => {
    const api = fakeFetch(200, { version: "v", models: {}, rubric_ready: true });
    const status = await getWritingStatus(api.fetchImpl);
    expect(api.calls[0].url).toBe("/api/backend/writing/status");
    expect(status.rubric_ready).toBe(true);
  });
});

describe("assessWriting", () => {
  it("gửi đề và bài, không gửi mode (route trung gian tự đặt)", async () => {
    const api = fakeFetch(200, { status: "final" });
    await assessWriting({ promptText: "P", essayText: "E", attemptId: "att_1" }, api.fetchImpl);
    expect(api.calls[0].url).toBe("/api/backend/writing/assess");
    expect(api.calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(api.calls[0].init?.body))).toEqual({ prompt_text: "P", essay_text: "E", attempt_id: "att_1" });
  });

  it("lỗi 400 của Writing (khoá error là câu tiếng Việt) hiện nguyên văn", async () => {
    const api = fakeFetch(400, { error: "prompt_text: không được để trống" });
    await expect(assessWriting({ promptText: "", essayText: "E" }, api.fetchImpl)).rejects.toMatchObject({
      status: 400,
      message: "prompt_text: không được để trống",
    });
  });
});
