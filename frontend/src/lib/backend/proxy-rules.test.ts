import { describe, expect, it } from "vitest";
import { isUuid, resolveBackendRoute } from "./proxy-rules";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";
const ANSWER = "9c1e4f52-7a3b-4d6e-8f10-a2b3c4d5e6f7";

const path = (method: string, segments: string[]) => resolveBackendRoute(method, segments)?.path ?? null;

describe("isUuid", () => {
  it("nhận UUID và từ chối chuỗi khác", () => {
    expect(isUuid(ID)).toBe(true);
    expect(isUuid("abc")).toBe(false);
    expect(isUuid(`${ID}?x=1`)).toBe(false);
  });
});

describe("resolveBackendRoute · UC-04", () => {
  it("cho phép tạo bài bằng POST /exercises, body JSON", () => {
    expect(resolveBackendRoute("POST", ["exercises"])).toEqual({ target: "exercises", path: "/api/exercises", body: "json" });
  });

  it("cho phép liệt kê bài bằng GET /exercises, không có body", () => {
    expect(resolveBackendRoute("GET", ["exercises"])).toEqual({ target: "exercises", path: "/api/exercises", body: "none" });
  });

  it("cho phép đọc bài, đáp án và trace bằng GET với UUID, không có body", () => {
    expect(resolveBackendRoute("GET", ["exercises", ID])).toEqual({ target: "exercises", path: `/api/exercises/${ID}`, body: "none" });
    expect(path("GET", ["exercises", ID, "answers"])).toBe(`/api/exercises/${ID}/answers`);
    expect(resolveBackendRoute("GET", ["traces", ID])?.target).toBe("exercises");
    expect(path("GET", ["traces", ID])).toBe(`/api/traces/${ID}`);
  });

  it("cho phép đọc lượt người nói, audio đã kiểm chứng và mốc thời gian của bài Listening bằng GET", () => {
    expect(resolveBackendRoute("GET", ["exercises", ID, "listening-turns"])).toEqual({ target: "exercises", path: `/api/exercises/${ID}/listening-turns`, body: "none" });
    expect(resolveBackendRoute("GET", ["exercises", ID, "audio"])).toEqual({ target: "exercises", path: `/api/exercises/${ID}/audio`, body: "none" });
    expect(resolveBackendRoute("GET", ["exercises", ID, "audio", "timings"])).toEqual({ target: "exercises", path: `/api/exercises/${ID}/audio/timings`, body: "none" });
  });

  it("lượt người nói và audio: từ chối method khác (kể cả POST tạo audio), id không phải UUID, đường dẫn thừa", () => {
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      expect(path(method, ["exercises", ID, "listening-turns"])).toBeNull();
      expect(path(method, ["exercises", ID, "audio"])).toBeNull();
      expect(path(method, ["exercises", ID, "audio", "timings"])).toBeNull();
    }
    expect(path("GET", ["exercises", "abc", "listening-turns"])).toBeNull();
    expect(path("GET", ["exercises", "..", "audio"])).toBeNull();
    expect(path("GET", ["exercises", `${ID}x`, "audio", "timings"])).toBeNull();
    expect(path("GET", ["exercises", ID, "audio", "verify"])).toBeNull();
    expect(path("GET", ["exercises", ID, "audio", "timings", "extra"])).toBeNull();
    expect(path("GET", ["exercises", ID, "listening-turns", "extra"])).toBeNull();
    expect(path("GET", ["traces", ID, "audio"])).toBeNull();
    expect(path("GET", ["attempts", ID, "audio", "timings"])).toBeNull();
    expect(path("GET", ["listening", "turns"])).toBeNull();
  });

  it("từ chối sai phương thức", () => {
    expect(path("PUT", ["exercises"])).toBeNull();
    expect(path("POST", ["exercises", ID])).toBeNull();
    expect(path("DELETE", ["traces", ID])).toBeNull();
  });

  it("từ chối id không phải UUID (chặn chèn đường dẫn)", () => {
    expect(path("GET", ["exercises", ".."])).toBeNull();
    expect(path("GET", ["exercises", "../health"])).toBeNull();
    expect(path("GET", ["traces", "abc"])).toBeNull();
    expect(path("GET", ["exercises", `${ID}?x=1`])).toBeNull();
    expect(path("GET", ["exercises?skill=reading"])).toBeNull();
  });

  it("từ chối endpoint không nằm trong danh sách", () => {
    expect(path("GET", ["health"])).toBeNull();
    expect(path("GET", ["docs"])).toBeNull();
    expect(path("GET", ["exercises", ID, "answers", "extra"])).toBeNull();
    expect(path("GET", [])).toBeNull();
  });
});

describe("resolveBackendRoute · Speaking", () => {
  const cases: [string, string[], string, string][] = [
    ["GET", ["speaking", "cue-cards"], "/api/cue-cards", "none"],
    ["GET", ["speaking", "capabilities"], "/api/exam/capabilities", "none"],
    ["POST", ["speaking", "sessions"], "/api/exam/sessions", "json"],
    ["GET", ["speaking", "sessions", ID], `/api/exam/sessions/${ID}`, "none"],
    ["POST", ["speaking", "sessions", ID, "actions"], `/api/exam/sessions/${ID}/actions`, "json"],
    ["POST", ["speaking", "sessions", ID, "text"], `/api/exam/sessions/${ID}/text`, "json"],
    ["POST", ["speaking", "sessions", ID, "voice"], `/api/exam/sessions/${ID}/voice`, "multipart"],
    ["GET", ["speaking", "sessions", ID, "audio", ANSWER], `/api/exam/sessions/${ID}/audio/${ANSWER}`, "none"],
    ["POST", ["speaking", "sessions", ID, "assessment"], `/api/exam/sessions/${ID}/assessment`, "json"],
    ["GET", ["speaking", "sessions", ID, "export"], `/api/exam/sessions/${ID}/export`, "none"],
  ];

  it.each(cases)("cho phép %s %j", (method, segments, upstreamPath, body) => {
    expect(resolveBackendRoute(method, segments)).toEqual({ target: "speaking", path: upstreamPath, body });
  });

  it("chặn teacher-review (backend không kiểm quyền) và các endpoint không có màn nhận", () => {
    for (const method of ["GET", "POST"]) {
      expect(path(method, ["speaking", "sessions", ID, "teacher-review"])).toBeNull();
      expect(path(method, ["speaking", "sessions", ID, "weakness-profile"])).toBeNull();
      expect(path(method, ["speaking", "sessions", ID, "attempt-audio"])).toBeNull();
      expect(path(method, ["speaking", "rubric", "search"])).toBeNull();
      expect(path(method, ["speaking", "transcribe"])).toBeNull();
      expect(path(method, ["speaking", "samples"])).toBeNull();
      expect(path(method, ["speaking", "database-schema"])).toBeNull();
      expect(path(method, ["speaking", "health"])).toBeNull();
    }
  });

  it("từ chối sai phương thức", () => {
    expect(path("GET", ["speaking", "sessions"])).toBeNull();
    expect(path("GET", ["speaking", "sessions", ID, "actions"])).toBeNull();
    expect(path("GET", ["speaking", "sessions", ID, "voice"])).toBeNull();
    expect(path("POST", ["speaking", "sessions", ID])).toBeNull();
    expect(path("POST", ["speaking", "sessions", ID, "audio", ANSWER])).toBeNull();
    expect(path("DELETE", ["speaking", "sessions", ID])).toBeNull();
  });

  it("từ chối id không phải UUID và đường dẫn thừa", () => {
    expect(path("GET", ["speaking", "sessions", ".."])).toBeNull();
    expect(path("GET", ["speaking", "sessions", "abc"])).toBeNull();
    expect(path("POST", ["speaking", "sessions", "../x", "actions"])).toBeNull();
    expect(path("GET", ["speaking", "sessions", ID, "audio", "../x"])).toBeNull();
    expect(path("GET", ["speaking", "sessions", ID, "audio", ANSWER, "extra"])).toBeNull();
    expect(path("GET", ["speaking", "cue-cards", "extra"])).toBeNull();
    expect(path("GET", ["speaking"])).toBeNull();
  });
});

describe("resolveBackendRoute · Writing", () => {
  it("cho phép GET status và POST assess", () => {
    expect(resolveBackendRoute("GET", ["writing", "status"])).toEqual({ target: "writing", path: "/api/status", body: "none" });
    expect(resolveBackendRoute("POST", ["writing", "assess"])).toEqual({ target: "writing", path: "/api/assess", body: "writing-assess" });
  });

  it("từ chối sai phương thức và đường dẫn lạ", () => {
    expect(path("POST", ["writing", "status"])).toBeNull();
    expect(path("GET", ["writing", "assess"])).toBeNull();
    expect(path("GET", ["writing", "runs"])).toBeNull();
    expect(path("GET", ["writing", "status", "extra"])).toBeNull();
    expect(path("GET", ["writing"])).toBeNull();
  });
});

describe("resolveBackendRoute · lượt làm Reading/Listening", () => {
  const cases: [string, string[], string, string][] = [
    ["POST", ["exercises", ID, "attempts"], `/api/exercises/${ID}/attempts`, "none"],
    ["GET", ["attempts", ID], `/api/attempts/${ID}`, "none"],
    ["PATCH", ["attempts", ID, "answers"], `/api/attempts/${ID}/answers`, "json"],
    ["POST", ["attempts", ID, "submit"], `/api/attempts/${ID}/submit`, "json"],
  ];

  it.each(cases)("cho phép %s %j", (method, segments, upstreamPath, body) => {
    expect(resolveBackendRoute(method, segments)).toEqual({ target: "exercises", path: upstreamPath, body });
  });

  it("từ chối id không phải UUID", () => {
    expect(path("POST", ["exercises", "..", "attempts"])).toBeNull();
    expect(path("GET", ["attempts", "abc"])).toBeNull();
    expect(path("PATCH", ["attempts", "../x", "answers"])).toBeNull();
    expect(path("POST", ["attempts", `${ID}?x=1`, "submit"])).toBeNull();
  });

  it("từ chối sai phương thức", () => {
    expect(path("GET", ["exercises", ID, "attempts"])).toBeNull();
    expect(path("POST", ["attempts", ID])).toBeNull();
    expect(path("PATCH", ["attempts", ID])).toBeNull();
    expect(path("POST", ["attempts", ID, "answers"])).toBeNull();
    expect(path("GET", ["attempts", ID, "submit"])).toBeNull();
    expect(path("PATCH", ["exercises", ID])).toBeNull();
    expect(path("DELETE", ["attempts", ID])).toBeNull();
  });

  it("từ chối đường dẫn thừa hoặc lạ", () => {
    expect(path("GET", ["attempts"])).toBeNull();
    expect(path("POST", ["attempts"])).toBeNull();
    expect(path("PATCH", ["attempts", ID, "answers", "extra"])).toBeNull();
    expect(path("POST", ["attempts", ID, "grade"])).toBeNull();
  });
});

describe("resolveBackendRoute · tiền tố lạ", () => {
  it("từ chối mọi tiền tố ngoài exercises, traces, speaking, writing", () => {
    expect(path("GET", ["admin", "status"])).toBeNull();
    expect(path("GET", ["Speaking", "cue-cards"])).toBeNull();
  });
});
