/**
 * Chuyển phản hồi lỗi của backend thành thông báo hiển thị được.
 * Quy tắc (ui-rules #7): thông điệp tiếng Việt của backend hiện nguyên văn, kể cả `provider_error`.
 * Hình dạng lỗi:
 * - UC-04 sinh bài: `{ error, message, trace_id }` (400, 422, 503); CSDL chưa sẵn sàng: 503 `{ error, message }`
 * - UC-04 không tìm thấy / token sai: `{ detail: "<tiếng Anh>" }` (404, 401); request sai kiểu: 422 `{ detail: [...] }`
 * - Speaking và route trung gian (413, 400): `{ detail: "<tiếng Việt>" }`
 * - Writing 400: `{ error: "<tiếng Việt>" }`, không có `message`
 * - Route trung gian 502, 504: `{ error, message }`
 */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null = null,
    readonly traceId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ErrorBody = { error?: unknown; message?: unknown; trace_id?: unknown; detail?: unknown };

const asString = (value: unknown) => (typeof value === "string" && value.trim() ? value : null);

/** Câu tiếng Việt có dấu (ngoài ASCII). Câu tiếng Anh kỹ thuật như "Exercise not found" vẫn đổi sang câu tiếng Việt. */
const isVietnamese = (text: string | null): text is string => text !== null && /[^\x00-\x7F]/.test(text);

export function toApiError(status: number, body: unknown): ApiError {
  const data: ErrorBody = body && typeof body === "object" ? (body as ErrorBody) : {};
  const code = asString(data.error);
  const message = asString(data.message);
  const detail = asString(data.detail);
  const traceId = asString(data.trace_id);

  if (status === 0) return new ApiError("Không kết nối được backend.", 0);
  if (code && message) return new ApiError(message, status, code, traceId);
  if (isVietnamese(detail)) return new ApiError(detail, status);
  if (isVietnamese(code)) return new ApiError(code, status);
  if (status === 404) return new ApiError("Không tìm thấy bài.", status);
  if (status === 401) return new ApiError("Backend yêu cầu token hợp lệ (API_TOKEN).", status);
  if (status === 422) return new ApiError("Yêu cầu không hợp lệ.", status);
  if (status === 504) return new ApiError("Backend phản hồi quá lâu. Thử lại sau.", status);
  return new ApiError(`Lỗi không xác định (HTTP ${status}).`, status);
}
