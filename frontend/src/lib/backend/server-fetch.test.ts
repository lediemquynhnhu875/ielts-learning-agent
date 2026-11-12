import { afterEach, describe, expect, it, vi } from "vitest";
import type { ForwardConfig } from "./forward";
import { backendConfig, createServerFetch } from "./server-fetch";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";
const base: ForwardConfig = {
  backendUrl: "http://127.0.0.1:8000",
  token: "",
  speakingUrl: "http://127.0.0.1:8010",
  writingUrl: "http://127.0.0.1:8765",
  writingMode: "live",
  timeoutMs: 1000,
};

function fakeBackend() {
  const calls: { url: string; auth: string | null }[] = [];
  const fetchImpl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), auth: new Headers(init?.headers).get("authorization") });
    return new Response(JSON.stringify({ id: ID }), { status: 200 });
  }) as typeof fetch;
  return { calls, fetchImpl };
}

describe("createServerFetch", () => {
  it("đổi đường dẫn /api/backend/... sang địa chỉ backend thật, kèm token phía server", async () => {
    const backend = fakeBackend();
    const serverFetch = createServerFetch({ ...base, token: "secret", fetchImpl: backend.fetchImpl });
    const res = await serverFetch(`/api/backend/exercises/${ID}/answers`, { method: "GET" });
    expect(res.status).toBe(200);
    expect(backend.calls).toEqual([{ url: `http://127.0.0.1:8000/api/exercises/${ID}/answers`, auth: "Bearer secret" }]);
  });

  it("vẫn chặn đường dẫn ngoài danh sách cho phép", async () => {
    const backend = fakeBackend();
    const serverFetch = createServerFetch({ ...base, fetchImpl: backend.fetchImpl });
    const res = await serverFetch("/api/backend/health", { method: "GET" });
    expect(res.status).toBe(404);
    expect(backend.calls).toHaveLength(0);
  });
});

describe("backendConfig", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("mặc định: UC-04 :8000, Speaking :8010, Writing :8765, mode live", () => {
    for (const name of ["BACKEND_URL", "API_TOKEN", "SPEAKING_BACKEND_URL", "WRITING_BACKEND_URL", "WRITING_MODE"]) vi.stubEnv(name, "");
    expect(backendConfig()).toMatchObject({
      backendUrl: "http://127.0.0.1:8000",
      token: "",
      speakingUrl: "http://127.0.0.1:8010",
      writingUrl: "http://127.0.0.1:8765",
      writingMode: "live",
    });
  });

  it("đọc địa chỉ từ biến môi trường phía server", () => {
    vi.stubEnv("SPEAKING_BACKEND_URL", "http://10.0.0.5:9010");
    vi.stubEnv("WRITING_BACKEND_URL", "http://10.0.0.6:9765");
    expect(backendConfig()).toMatchObject({ speakingUrl: "http://10.0.0.5:9010", writingUrl: "http://10.0.0.6:9765" });
  });

  it("chỉ WRITING_MODE=demo mới bật demo; giá trị lạ vẫn là live", () => {
    vi.stubEnv("WRITING_MODE", "demo");
    expect(backendConfig().writingMode).toBe("demo");
    vi.stubEnv("WRITING_MODE", "DEMO ");
    expect(backendConfig().writingMode).toBe("live");
    vi.stubEnv("WRITING_MODE", "bất kỳ");
    expect(backendConfig().writingMode).toBe("live");
  });
});
