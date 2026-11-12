import { describe, expect, it } from "vitest";
import { createAttempt, getAttempt, saveAnswers, submitAttempt } from "./attempts";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";
const QUESTION = "9c1e4f52-7a3b-4d6e-8f10-a2b3c4d5e6f7";
const TOKEN = "attempt-secret";

function fakeFetch(status: number, body: unknown) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fetchImpl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  return { calls, fetchImpl };
}

const headers = (init?: RequestInit) => new Headers(init?.headers);

describe("attempts client", () => {
  it("createAttempt gửi POST exercises/{id}/attempts, không có token", async () => {
    const api = fakeFetch(201, { attempt_id: ID, attempt_token: TOKEN });
    const created = await createAttempt(ID, api.fetchImpl);
    expect(api.calls[0].url).toBe(`/api/backend/exercises/${ID}/attempts`);
    expect(api.calls[0].init?.method).toBe("POST");
    expect(headers(api.calls[0].init).has("x-attempt-token")).toBe(false);
    expect(created.attempt_token).toBe(TOKEN);
  });

  it("getAttempt gửi GET attempts/{id} kèm X-Attempt-Token", async () => {
    const api = fakeFetch(200, { attempt_id: ID, status: "in_progress" });
    await getAttempt(ID, TOKEN, api.fetchImpl);
    expect(api.calls[0].url).toBe(`/api/backend/attempts/${ID}`);
    expect(api.calls[0].init?.method).toBe("GET");
    expect(headers(api.calls[0].init).get("x-attempt-token")).toBe(TOKEN);
  });

  it("saveAnswers gửi PATCH attempts/{id}/answers với map đáp án, null là xoá", async () => {
    const api = fakeFetch(200, { attempt_id: ID });
    await saveAnswers(ID, TOKEN, { [QUESTION]: null }, api.fetchImpl);
    const init = api.calls[0].init;
    expect(api.calls[0].url).toBe(`/api/backend/attempts/${ID}/answers`);
    expect(init?.method).toBe("PATCH");
    expect(headers(init).get("x-attempt-token")).toBe(TOKEN);
    expect(headers(init).get("content-type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual({ answers: { [QUESTION]: null } });
  });

  it("submitAttempt gửi POST attempts/{id}/submit với toàn bộ đáp án", async () => {
    const api = fakeFetch(200, { attempt_id: ID, status: "submitted" });
    await submitAttempt(ID, TOKEN, { [QUESTION]: "NOT GIVEN" }, api.fetchImpl);
    const init = api.calls[0].init;
    expect(api.calls[0].url).toBe(`/api/backend/attempts/${ID}/submit`);
    expect(init?.method).toBe("POST");
    expect(headers(init).get("x-attempt-token")).toBe(TOKEN);
    expect(JSON.parse(String(init?.body))).toEqual({ answers: { [QUESTION]: "NOT GIVEN" } });
  });

  it("lỗi nghiệp vụ giữ mã error để màn làm bài xử lý 409 attempt_submitted", async () => {
    const api = fakeFetch(409, { error: "attempt_submitted", message: "Submitted answers cannot be edited" });
    await expect(saveAnswers(ID, TOKEN, {}, api.fetchImpl)).rejects.toMatchObject({
      status: 409,
      code: "attempt_submitted",
      message: "Submitted answers cannot be edited",
    });
  });
});
