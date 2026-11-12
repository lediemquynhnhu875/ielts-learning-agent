import { describe, expect, it } from "vitest";
import { createExercise, getExercise, listExercises } from "./client";
import { ApiError } from "./errors";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";

function fakeFetch(response: Response | Error) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const impl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    if (response instanceof Error) throw response;
    return response;
  }) as typeof fetch;
  return { calls, impl };
}

describe("listExercises", () => {
  const page = { items: [], total: 0, limit: 20, offset: 0 };

  it("gọi GET exercises qua route trung gian, kèm skill, q, limit, offset", async () => {
    const f = fakeFetch(new Response(JSON.stringify(page)));
    expect(await listExercises({ skill: "listening", q: "  river & delta ", limit: 20, offset: 40 }, f.impl)).toEqual(page);
    expect(f.calls[0].url).toBe("/api/backend/exercises?skill=listening&q=river+%26+delta&limit=20&offset=40");
    expect(f.calls[0].init?.method).toBe("GET");
  });

  it("bỏ tham số không dùng: không lọc kỹ năng, ô tìm trống", async () => {
    const f = fakeFetch(new Response(JSON.stringify(page)));
    await listExercises({ q: "   ", limit: 20, offset: 0 }, f.impl);
    expect(f.calls[0].url).toBe("/api/backend/exercises?limit=20&offset=0");
  });

  it("lỗi backend thành ApiError giữ thông điệp", async () => {
    const f = fakeFetch(new Response(JSON.stringify({ error: "database_unavailable", message: "PostgreSQL chưa sẵn sàng." }), { status: 503 }));
    await expect(listExercises({ limit: 20, offset: 0 }, f.impl)).rejects.toMatchObject({ status: 503, message: "PostgreSQL chưa sẵn sàng." });
  });
});

describe("api client", () => {
  it("createExercise gửi POST qua route trung gian với body đúng tên trường của backend", async () => {
    const f = fakeFetch(new Response(JSON.stringify({ id: ID }), { status: 201 }));
    const result = await createExercise(
      { skill: "listening", topic: "Floating markets", target_band: 6.5, question_count: 10, completion_word_limit: 2 },
      f.impl,
    );
    expect(result).toEqual({ id: ID });
    expect(f.calls[0].url).toBe("/api/backend/exercises");
    expect(f.calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(f.calls[0].init?.body))).toEqual({
      skill: "listening",
      topic: "Floating markets",
      target_band: 6.5,
      question_count: 10,
      completion_word_limit: 2,
    });
  });

  it("ném ApiError với thông báo của backend khi lỗi", async () => {
    const f = fakeFetch(
      new Response(JSON.stringify({ error: "unsafe_topic", message: "Chủ đề không phù hợp.", trace_id: ID }), { status: 400 }),
    );
    const error = await createExercise(
      { skill: "reading", topic: "x x x", target_band: 6, question_count: 10, completion_word_limit: 2 },
      f.impl,
    ).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 400, message: "Chủ đề không phù hợp.", traceId: ID });
  });

  it("getExercise gọi đúng đường dẫn và báo không kết nối được khi fetch lỗi mạng", async () => {
    const f = fakeFetch(new TypeError("Failed to fetch"));
    const error = await getExercise(ID, f.impl).catch((e) => e);
    expect(f.calls[0].url).toBe(`/api/backend/exercises/${ID}`);
    expect(error).toMatchObject({ status: 0, message: "Không kết nối được backend." });
  });
});
