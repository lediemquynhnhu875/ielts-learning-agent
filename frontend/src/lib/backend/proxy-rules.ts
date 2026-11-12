/**
 * Danh sách endpoint backend mà route trung gian `/api/backend/...` được phép chuyển tiếp.
 * Ba backend, mỗi backend một tiền tố:
 * - `exercises`, `traces`, `attempts`: UC-04 (docs/uc04.md, docs/reading-listening-practice.md), cổng 8000;
 *   kèm lượt người nói và audio đã kiểm chứng của bài Listening (docs/listening-speaker-turns.md, docs/listening-azure-speech.md).
 * - `speaking/...`: agent Speaking, cổng 8010 (`/api/exam/...`).
 * - `writing/...`: prototype Writing, cổng 8765.
 * Mọi đường dẫn khác bị từ chối. `id` phải là UUID (backend cũng khai báo kiểu UUID), chặn chèn đường dẫn.
 *
 * Không mở: `teacher-review` của Speaking (backend không kiểm quyền) và các endpoint không có màn nhận
 * trong tài liệu (tra rubric, transcribe, samples, weakness-profile, attempt-audio, database-schema).
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const isUuid = (value: string) => UUID.test(value);

export type BackendTarget = "exercises" | "speaking" | "writing";

/**
 * Cách xử lý body của request:
 * - `none`: không có body.
 * - `json`: chuyển nguyên chuỗi JSON.
 * - `multipart`: chuyển nguyên luồng byte và content-type (có boundary), dùng cho gửi audio.
 * - `writing-assess`: JSON mà route trung gian tự đặt lại `mode` (xem forward.ts).
 */
export type BodyKind = "none" | "json" | "multipart" | "writing-assess";

export type BackendRoute = { target: BackendTarget; path: string; body: BodyKind };

const route = (target: BackendTarget, path: string, body: BodyKind): BackendRoute => ({ target, path, body });

function resolveExercises(method: string, segments: string[]): BackendRoute | null {
  const [resource, id, sub, leaf, ...rest] = segments;
  if (rest.length > 0) return null;
  // Đường dẫn bốn đoạn duy nhất được mở: GET exercises/{id}/audio/timings.
  const timings = method === "GET" && resource === "exercises" && sub === "audio" && leaf === "timings";
  if (leaf !== undefined && !timings) return null;

  if (method === "POST" && resource === "exercises" && id === undefined) return route("exercises", "/api/exercises", "json");
  if (method === "GET" && resource === "exercises" && id === undefined) return route("exercises", "/api/exercises", "none");
  if (id === undefined || !UUID.test(id)) return null;

  // Lượt làm Reading/Listening (docs/reading-listening-practice.md).
  if (method === "POST" && resource === "exercises" && sub === "attempts") {
    return route("exercises", `/api/exercises/${id}/attempts`, "none");
  }
  if (resource === "attempts") {
    if (method === "GET" && sub === undefined) return route("exercises", `/api/attempts/${id}`, "none");
    if (method === "PATCH" && sub === "answers") return route("exercises", `/api/attempts/${id}/answers`, "json");
    if (method === "POST" && sub === "submit") return route("exercises", `/api/attempts/${id}/submit`, "json");
    return null;
  }
  if (method !== "GET") return null;

  if (resource === "exercises" && sub === undefined) return route("exercises", `/api/exercises/${id}`, "none");
  if (resource === "exercises" && sub === "answers") return route("exercises", `/api/exercises/${id}/answers`, "none");
  // Listening: chỉ mở GET (đọc). Các POST tạo/kiểm chứng audio là API biên soạn, cố ý không mở.
  if (resource === "exercises" && sub === "listening-turns") return route("exercises", `/api/exercises/${id}/listening-turns`, "none");
  if (timings) return route("exercises", `/api/exercises/${id}/audio/timings`, "none");
  if (resource === "exercises" && sub === "audio") return route("exercises", `/api/exercises/${id}/audio`, "none");
  if (resource === "traces" && sub === undefined) return route("exercises", `/api/traces/${id}`, "none");
  return null;
}

/** `segments` đã bỏ tiền tố `speaking`. */
function resolveSpeaking(method: string, segments: string[]): BackendRoute | null {
  const [first, id, action, answerId, ...rest] = segments;
  if (rest.length > 0) return null;

  if (first === "cue-cards" && segments.length === 1) {
    return method === "GET" ? route("speaking", "/api/cue-cards", "none") : null;
  }
  if (first === "capabilities" && segments.length === 1) {
    return method === "GET" ? route("speaking", "/api/exam/capabilities", "none") : null;
  }
  if (first !== "sessions") return null;

  if (id === undefined) return method === "POST" ? route("speaking", "/api/exam/sessions", "json") : null;
  if (!UUID.test(id)) return null;
  const base = `/api/exam/sessions/${id}`;

  if (action === undefined) return method === "GET" ? route("speaking", base, "none") : null;
  if (action === "audio") {
    return method === "GET" && answerId !== undefined && UUID.test(answerId)
      ? route("speaking", `${base}/audio/${answerId}`, "none")
      : null;
  }
  if (answerId !== undefined) return null;

  if (method === "POST") {
    if (action === "actions" || action === "text" || action === "assessment") return route("speaking", `${base}/${action}`, "json");
    if (action === "voice") return route("speaking", `${base}/voice`, "multipart");
  }
  if (method === "GET" && action === "export") return route("speaking", `${base}/export`, "none");
  return null;
}

/** `segments` đã bỏ tiền tố `writing`. */
function resolveWriting(method: string, segments: string[]): BackendRoute | null {
  if (segments.length !== 1) return null;
  if (method === "GET" && segments[0] === "status") return route("writing", "/api/status", "none");
  if (method === "POST" && segments[0] === "assess") return route("writing", "/api/assess", "writing-assess");
  return null;
}

/** Trả về backend, đường dẫn thật và cách xử lý body, hoặc `null` nếu không được phép. */
export function resolveBackendRoute(method: string, segments: string[]): BackendRoute | null {
  const [prefix, ...rest] = segments;
  if (prefix === "speaking") return resolveSpeaking(method, rest);
  if (prefix === "writing") return resolveWriting(method, rest);
  return resolveExercises(method, segments);
}
