import { toApiError } from "./errors";
import type { Exercise, ExerciseAnswers, ExerciseList, ExerciseListParams, GenerateRequest, Trace } from "./types";

/** Mọi lời gọi đi qua route trung gian của Next.js (backend không bật CORS). */
export const BASE = "/api/backend";

/** Gọi route trung gian; lỗi HTTP và lỗi mạng đổi thành ApiError. Dùng chung cho mọi client API. */
export async function request<T>(path: string, init: RequestInit, fetchImpl: typeof fetch): Promise<T> {
  let response: Response;
  try {
    response = await fetchImpl(`${BASE}${path}`, { ...init, cache: "no-store" });
  } catch {
    throw toApiError(0, null);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, body);
  return body as T;
}

export function createExercise(input: GenerateRequest, fetchImpl: typeof fetch = fetch) {
  return request<Exercise>(
    "/exercises",
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(input) },
    fetchImpl,
  );
}

/** Liệt kê bài Reading/Listening đã kiểm chứng, mới nhất trước. Tham số trống thì không gửi. */
export function listExercises({ skill, q, limit, offset }: ExerciseListParams, fetchImpl: typeof fetch = fetch) {
  const search = new URLSearchParams();
  if (skill) search.set("skill", skill);
  if (q?.trim()) search.set("q", q.trim());
  search.set("limit", String(limit));
  search.set("offset", String(offset));
  return request<ExerciseList>(`/exercises?${search}`, { method: "GET" }, fetchImpl);
}

export function getExercise(id: string, fetchImpl: typeof fetch = fetch) {
  return request<Exercise>(`/exercises/${id}`, { method: "GET" }, fetchImpl);
}

export function getExerciseAnswers(id: string, fetchImpl: typeof fetch = fetch) {
  return request<ExerciseAnswers>(`/exercises/${id}/answers`, { method: "GET" }, fetchImpl);
}

export function getTrace(traceId: string, fetchImpl: typeof fetch = fetch) {
  return request<Trace>(`/traces/${traceId}`, { method: "GET" }, fetchImpl);
}
