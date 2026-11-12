import { describe, expect, it } from "vitest";
import { forwardToBackend, type ForwardConfig } from "./forward";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";
const ANSWER = "9c1e4f52-7a3b-4d6e-8f10-a2b3c4d5e6f7";
const config: ForwardConfig = {
  backendUrl: "http://127.0.0.1:8000",
  token: "",
  speakingUrl: "http://127.0.0.1:8010",
  writingUrl: "http://127.0.0.1:8765",
  writingMode: "live",
  timeoutMs: 1000,
};

type Call = { url: string; init: RequestInit };

/** Backend giả: ghi lại lời gọi và trả phản hồi cho trước. */
function fakeBackend(response: Response | Error) {
  const calls: Call[] = [];
  const fetchImpl = async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    if (response instanceof Error) throw response;
    return response;
  };
  return { calls, fetchImpl: fetchImpl as typeof fetch };
}

const run = (request: Request, segments: string[], backend: ReturnType<typeof fakeBackend>, extra: Partial<ForwardConfig> = {}) =>
  forwardToBackend(request, segments, { ...config, ...extra, fetchImpl: backend.fetchImpl });

describe("forwardToBackend · UC-04", () => {
  it("trả 404 và không gọi backend khi đường dẫn không được phép", async () => {
    const backend = fakeBackend(new Response("{}"));
    const res = await run(new Request("http://x/api/backend/health"), ["health"], backend);
    expect(res.status).toBe(404);
    expect(backend.calls).toHaveLength(0);
  });

  it("chuyển tiếp GET tới đúng địa chỉ backend và giữ nguyên mã trạng thái, body", async () => {
    const backend = fakeBackend(new Response(JSON.stringify({ detail: "Exercise not found" }), { status: 404 }));
    const res = await run(new Request(`http://x/api/backend/exercises/${ID}`), ["exercises", ID], backend);
    expect(backend.calls[0].url).toBe(`http://127.0.0.1:8000/api/exercises/${ID}`);
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ detail: "Exercise not found" });
  });

  it.each(["", "?skill=listening&target_band=6.5&q=C%E1%BA%A7n%20Gi%E1%BB%9D%20%26%20%25_&limit=10&offset=20"])(
    "chuyển tiếp GET danh sách cùng query nguyên vẹn: %s",
    async (search) => {
      const page = { items: [], total: 0, limit: 10, offset: 20 };
      const backend = fakeBackend(new Response(JSON.stringify(page)));
      const res = await run(new Request(`http://x/api/backend/exercises${search}`), ["exercises"], backend);
      expect(backend.calls).toHaveLength(1);
      expect(backend.calls[0].url).toBe(`http://127.0.0.1:8000/api/exercises${search}`);
      expect(backend.calls[0].init.method).toBe("GET");
      expect(backend.calls[0].init.body).toBeUndefined();
      expect(backend.calls[0].init.cache).toBe("no-store");
      expect(res.status).toBe(200);
      expect(await res.json()).toEqual(page);
    },
  );

  it.each(["", "server-token"])("GET danh sách chỉ dùng token từ cấu hình server: %s", async (token) => {
    const backend = fakeBackend(new Response("{}"));
    const request = new Request("http://x/api/backend/exercises", { headers: { authorization: "Bearer browser-token" } });
    await run(request, ["exercises"], backend, { token });
    expect(new Headers(backend.calls[0].init.headers).get("authorization")).toBe(token ? `Bearer ${token}` : null);
  });

  it.each([
    ["GET", ["exercises", ID], `/api/exercises/${ID}`, config.backendUrl],
    ["GET", ["traces", ID], `/api/traces/${ID}`, config.backendUrl],
    ["GET", ["speaking", "cue-cards"], "/api/cue-cards", config.speakingUrl],
    ["GET", ["writing", "status"], "/api/status", config.writingUrl],
    ["POST", ["exercises"], "/api/exercises", config.backendUrl],
  ] as const)("giữ nguyên việc bỏ query của %s %j", async (method, segments, upstreamPath, base) => {
    const backend = fakeBackend(new Response("{}"));
    const request = new Request(`http://x/api/backend/${segments.join("/")}?q=ignored`, { method });
    await run(request, [...segments], backend);
    expect(backend.calls[0].url).toBe(`${base}${upstreamPath}`);
  });

  it("chuyển tiếp body của POST và gắn token khi có cấu hình", async () => {
    const backend = fakeBackend(new Response(JSON.stringify({ id: ID }), { status: 201 }));
    const body = JSON.stringify({ skill: "reading", topic: "Mangroves" });
    const req = new Request("http://x/api/backend/exercises", { method: "POST", body, headers: { "content-type": "application/json" } });
    const res = await run(req, ["exercises"], backend, { token: "secret" });
    const headers = new Headers(backend.calls[0].init.headers);
    expect(res.status).toBe(201);
    expect(backend.calls[0].init.method).toBe("POST");
    expect(backend.calls[0].init.body).toBe(body);
    expect(headers.get("authorization")).toBe("Bearer secret");
  });

  it("không gửi header authorization khi không cấu hình token", async () => {
    const backend = fakeBackend(new Response("{}"));
    await run(new Request(`http://x/api/backend/traces/${ID}`), ["traces", ID], backend);
    expect(new Headers(backend.calls[0].init.headers).has("authorization")).toBe(false);
  });

  it("trả 502 khi không kết nối được backend", async () => {
    const backend = fakeBackend(new TypeError("fetch failed"));
    const res = await run(new Request(`http://x/api/backend/traces/${ID}`), ["traces", ID], backend);
    expect(res.status).toBe(502);
  });

  it("trả 504 khi backend phản hồi quá thời gian chờ", async () => {
    const backend = fakeBackend(new DOMException("timed out", "TimeoutError"));
    const res = await run(new Request(`http://x/api/backend/traces/${ID}`), ["traces", ID], backend);
    expect(res.status).toBe(504);
  });
});

describe("forwardToBackend · lượt làm Reading/Listening", () => {
  const TOKEN = "attempt-secret";

  it("PATCH đáp án chuyển body, X-Attempt-Token và bearer của UC-04", async () => {
    const backend = fakeBackend(new Response("{}"));
    const body = JSON.stringify({ answers: { [ANSWER]: "TRUE" } });
    const req = new Request(`http://x/api/backend/attempts/${ID}/answers`, {
      method: "PATCH",
      body,
      headers: { "x-attempt-token": TOKEN },
    });
    await run(req, ["attempts", ID, "answers"], backend, { token: "secret" });
    const headers = new Headers(backend.calls[0].init.headers);
    expect(backend.calls[0].url).toBe(`http://127.0.0.1:8000/api/attempts/${ID}/answers`);
    expect(backend.calls[0].init.method).toBe("PATCH");
    expect(backend.calls[0].init.body).toBe(body);
    expect(headers.get("x-attempt-token")).toBe(TOKEN);
    expect(headers.get("authorization")).toBe("Bearer secret");
  });

  it("GET lượt làm chuyển X-Attempt-Token", async () => {
    const backend = fakeBackend(new Response("{}"));
    const req = new Request(`http://x/api/backend/attempts/${ID}`, { headers: { "x-attempt-token": TOKEN } });
    await run(req, ["attempts", ID], backend);
    expect(new Headers(backend.calls[0].init.headers).get("x-attempt-token")).toBe(TOKEN);
  });

  it("không chuyển X-Attempt-Token ngoài /api/attempts/", async () => {
    const cases: [Request, string[]][] = [
      [new Request(`http://x/api/backend/exercises/${ID}/attempts`, { method: "POST", headers: { "x-attempt-token": TOKEN } }), ["exercises", ID, "attempts"]],
      [new Request(`http://x/api/backend/exercises/${ID}`, { headers: { "x-attempt-token": TOKEN } }), ["exercises", ID]],
      [new Request("http://x/api/backend/speaking/cue-cards", { headers: { "x-attempt-token": TOKEN } }), ["speaking", "cue-cards"]],
      [new Request("http://x/api/backend/writing/status", { headers: { "x-attempt-token": TOKEN } }), ["writing", "status"]],
    ];
    for (const [req, segments] of cases) {
      const backend = fakeBackend(new Response("{}"));
      await run(req, segments, backend);
      expect(new Headers(backend.calls[0].init.headers).has("x-attempt-token")).toBe(false);
    }
  });

  it("không đặt header khi trình duyệt không gửi token", async () => {
    const backend = fakeBackend(new Response("{}"));
    await run(new Request(`http://x/api/backend/attempts/${ID}`), ["attempts", ID], backend);
    expect(new Headers(backend.calls[0].init.headers).has("x-attempt-token")).toBe(false);
  });
});

describe("forwardToBackend · chọn backend", () => {
  it("Speaking đi tới SPEAKING_BACKEND_URL, không kèm API_TOKEN của UC-04", async () => {
    const backend = fakeBackend(new Response("[]"));
    await run(new Request("http://x/api/backend/speaking/cue-cards"), ["speaking", "cue-cards"], backend, { token: "secret" });
    expect(backend.calls[0].url).toBe("http://127.0.0.1:8010/api/cue-cards");
    expect(new Headers(backend.calls[0].init.headers).has("authorization")).toBe(false);
  });

  it("Writing đi tới WRITING_BACKEND_URL, không kèm API_TOKEN, bỏ dấu / cuối địa chỉ", async () => {
    const backend = fakeBackend(new Response("{}"));
    await run(new Request("http://x/api/backend/writing/status"), ["writing", "status"], backend, {
      token: "secret",
      writingUrl: "http://127.0.0.1:8765/",
    });
    expect(backend.calls[0].url).toBe("http://127.0.0.1:8765/api/status");
    expect(new Headers(backend.calls[0].init.headers).has("authorization")).toBe(false);
  });

  it("chặn teacher-review của Speaking, không gọi backend", async () => {
    const backend = fakeBackend(new Response("{}"));
    const req = new Request(`http://x/api/backend/speaking/sessions/${ID}/teacher-review`, { method: "POST", body: "{}" });
    const res = await run(req, ["speaking", "sessions", ID, "teacher-review"], backend);
    expect(res.status).toBe(404);
    expect(backend.calls).toHaveLength(0);
  });

  it("giữ nguyên thông điệp lỗi tiếng Việt của backend (mã trạng thái và body)", async () => {
    const detail = { detail: "Phiên đã kết thúc." };
    const backend = fakeBackend(new Response(JSON.stringify(detail), { status: 409, headers: { "content-type": "application/json" } }));
    const req = new Request(`http://x/api/backend/speaking/sessions/${ID}/actions`, { method: "POST", body: "{}" });
    const res = await run(req, ["speaking", "sessions", ID, "actions"], backend);
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual(detail);
  });

  it("POST JSON của Speaking giữ nguyên body và content-type JSON", async () => {
    const backend = fakeBackend(new Response("{}", { status: 201 }));
    const body = JSON.stringify({ mode: "text", kind: "practice" });
    const req = new Request("http://x/api/backend/speaking/sessions", { method: "POST", body });
    await run(req, ["speaking", "sessions"], backend);
    expect(backend.calls[0].init.body).toBe(body);
    expect(new Headers(backend.calls[0].init.headers).get("content-type")).toBe("application/json");
  });
});

describe("forwardToBackend · multipart và nhị phân (Speaking)", () => {
  function voiceRequest(extraHeaders: Record<string, string> = {}) {
    const form = new FormData();
    form.append("question_id", ID);
    form.append("audio", new Blob([new Uint8Array([0, 1, 2, 250, 251, 252])], { type: "audio/wav" }), "answer.wav");
    return new Request(`http://x/api/backend/speaking/sessions/${ID}/voice`, { method: "POST", body: form, headers: extraHeaders });
  }

  it("chuyển nguyên byte multipart và giữ content-type có boundary", async () => {
    const req = voiceRequest();
    const sentType = req.headers.get("content-type");
    const sentBytes = new Uint8Array(await req.clone().arrayBuffer());
    const backend = fakeBackend(new Response("{}"));
    await run(req, ["speaking", "sessions", ID, "voice"], backend);

    const call = backend.calls[0];
    expect(call.url).toBe(`http://127.0.0.1:8010/api/exam/sessions/${ID}/voice`);
    expect(sentType).toMatch(/^multipart\/form-data; boundary=/);
    expect(new Headers(call.init.headers).get("content-type")).toBe(sentType);
    expect((call.init as RequestInit & { duplex?: string }).duplex).toBe("half");
    const received = new Uint8Array(await new Response(call.init.body as BodyInit).arrayBuffer());
    expect(Array.from(received)).toEqual(Array.from(sentBytes));
  });

  it("trả 413 với thông điệp của backend khi audio khai báo quá 24 MB, không gọi backend", async () => {
    const backend = fakeBackend(new Response("{}"));
    const tooBig = String(24 * 1024 * 1024 + 65536 + 1);
    const res = await run(voiceRequest({ "content-length": tooBig }), ["speaking", "sessions", ID, "voice"], backend);
    expect(res.status).toBe(413);
    expect(await res.json()).toEqual({ detail: "File quá lớn. Giới hạn audio là 24 MB." });
    expect(backend.calls).toHaveLength(0);
  });

  it("trả 413 khi content-length không phải số", async () => {
    const backend = fakeBackend(new Response("{}"));
    const res = await run(voiceRequest({ "content-length": "abc" }), ["speaking", "sessions", ID, "voice"], backend);
    expect(res.status).toBe(413);
    expect(backend.calls).toHaveLength(0);
  });

  it("audio Listening: GET exercises/{id}/audio trả WAV nguyên vẹn kèm content-type, không chuyển query", async () => {
    const bytes = new Uint8Array([82, 73, 70, 70, 0, 255, 254]);
    const backend = fakeBackend(new Response(bytes, { headers: { "content-type": "audio/wav" } }));
    const res = await run(new Request(`http://x/api/backend/exercises/${ID}/audio?x=1`), ["exercises", ID, "audio"], backend);
    expect(backend.calls[0].url.endsWith(`/api/exercises/${ID}/audio`)).toBe(true);
    expect(res.headers.get("content-type")).toBe("audio/wav");
    expect(new Uint8Array(await res.arrayBuffer())).toEqual(bytes);
  });

  it("trả audio nhị phân nguyên vẹn kèm content-type", async () => {
    const bytes = new Uint8Array([0, 255, 1, 254, 2, 128]);
    const backend = fakeBackend(new Response(bytes, { headers: { "content-type": "audio/wav" } }));
    const res = await run(new Request(`http://x/api/backend/speaking/sessions/${ID}/audio/${ANSWER}`), ["speaking", "sessions", ID, "audio", ANSWER], backend);
    expect(res.headers.get("content-type")).toBe("audio/wav");
    expect(Array.from(new Uint8Array(await res.arrayBuffer()))).toEqual(Array.from(bytes));
    expect(new Headers(backend.calls[0].init.headers).get("accept")).toBe("*/*");
  });
});

describe("forwardToBackend · Writing", () => {
  const assess = (body: string) => new Request("http://x/api/backend/writing/assess", { method: "POST", body });
  const sentBody = (backend: ReturnType<typeof fakeBackend>) => JSON.parse(String(backend.calls[0].init.body));

  it("tự đặt mode theo WRITING_MODE (mặc định live), bỏ mode do trình duyệt gửi", async () => {
    const backend = fakeBackend(new Response("{}"));
    await run(assess(JSON.stringify({ mode: "demo", prompt_text: "P", essay_text: "E" })), ["writing", "assess"], backend);
    expect(backend.calls[0].url).toBe("http://127.0.0.1:8765/api/assess");
    expect(sentBody(backend)).toEqual({ mode: "live", prompt_text: "P", essay_text: "E" });
  });

  it("đặt mode khi trình duyệt không gửi, và dùng demo khi cấu hình WRITING_MODE=demo", async () => {
    const backend = fakeBackend(new Response("{}"));
    await run(assess(JSON.stringify({ prompt_text: "P", essay_text: "E", attempt_id: "a1" })), ["writing", "assess"], backend, { writingMode: "demo" });
    expect(sentBody(backend)).toEqual({ mode: "demo", prompt_text: "P", essay_text: "E", attempt_id: "a1" });
  });

  it("gửi content-type JSON và không chuyển Origin của trình duyệt", async () => {
    const backend = fakeBackend(new Response("{}"));
    const req = new Request("http://x/api/backend/writing/assess", { method: "POST", body: "{}", headers: { origin: "http://localhost:3000" } });
    await run(req, ["writing", "assess"], backend);
    const headers = new Headers(backend.calls[0].init.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.has("origin")).toBe(false);
  });

  it("trả 400 và không gọi backend khi body không phải JSON object", async () => {
    for (const body of ["không phải json", "[1,2]", "null", '"x"']) {
      const backend = fakeBackend(new Response("{}"));
      const res = await run(assess(body), ["writing", "assess"], backend);
      expect(res.status).toBe(400);
      expect(await res.json()).toEqual({ detail: "Body phải là một JSON object." });
      expect(backend.calls).toHaveLength(0);
    }
  });

  it("giữ nguyên lỗi của Writing (khoá error) khi chấm không thành", async () => {
    const backend = fakeBackend(new Response(JSON.stringify({ error: "Request quá lớn hoặc rỗng" }), { status: 400 }));
    const res = await run(assess("{}"), ["writing", "assess"], backend);
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "Request quá lớn hoặc rỗng" });
  });
});
