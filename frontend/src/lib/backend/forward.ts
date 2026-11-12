import { resolveBackendRoute, type BackendRoute } from "./proxy-rules";

export type WritingMode = "live" | "demo";

export type ForwardConfig = {
  /** Địa chỉ backend UC-04, chỉ đọc phía server (BACKEND_URL). */
  backendUrl: string;
  /** API_TOKEN của backend UC-04; rỗng là không gửi header. Không bao giờ lộ ra trình duyệt hay gửi sang backend khác. */
  token: string;
  /** Địa chỉ agent Speaking (SPEAKING_BACKEND_URL). */
  speakingUrl: string;
  /** Địa chỉ prototype Writing (WRITING_BACKEND_URL). */
  writingUrl: string;
  /** Chế độ chấm Writing do route trung gian quyết định (WRITING_MODE); trình duyệt không chọn được. */
  writingMode: WritingMode;
  timeoutMs: number;
  fetchImpl?: typeof fetch;
};

/** Giới hạn audio của backend Speaking (24 MB) cộng phần đệm multipart (64 KB), cùng giá trị với backend. */
const MAX_VOICE_BYTES = 24 * 1024 * 1024 + 65536;
const VOICE_TOO_LARGE = "File quá lớn. Giới hạn audio là 24 MB.";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const upstreamUrl = (route: BackendRoute, config: ForwardConfig) => {
  const base = route.target === "speaking" ? config.speakingUrl : route.target === "writing" ? config.writingUrl : config.backendUrl;
  return `${base.replace(/\/+$/, "")}${route.path}`;
};

type PreparedBody = { body?: BodyInit; contentType?: string; duplex?: "half" } | Response;

/** Dựng body gửi backend; trả `Response` (lỗi cho trình duyệt) khi request không hợp lệ. */
async function prepareBody(request: Request, route: BackendRoute, config: ForwardConfig): Promise<PreparedBody> {
  switch (route.body) {
    case "none":
      return {};
    case "json":
      return { body: await request.text(), contentType: "application/json" };
    case "multipart": {
      const declared = request.headers.get("content-length");
      if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > MAX_VOICE_BYTES)) {
        return json(413, { detail: VOICE_TOO_LARGE });
      }
      const contentType = request.headers.get("content-type") ?? undefined;
      return request.body ? { body: request.body, contentType, duplex: "half" } : { contentType };
    }
    case "writing-assess": {
      let payload: unknown;
      try {
        payload = JSON.parse(await request.text());
      } catch {
        payload = null;
      }
      if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
        return json(400, { detail: "Body phải là một JSON object." });
      }
      return { body: JSON.stringify({ ...payload, mode: config.writingMode }), contentType: "application/json" };
    }
  }
}

/**
 * Chuyển tiếp request từ trình duyệt tới backend UC-04, Speaking hoặc Writing.
 * Backend không bật CORS nên trình duyệt gọi qua route này; chỉ endpoint trong proxy-rules được đi qua.
 * Thông điệp lỗi của backend được giữ nguyên (mã trạng thái, body); chỉ lỗi kết nối và quá giờ do route này tự trả.
 */
export async function forwardToBackend(request: Request, segments: string[], config: ForwardConfig): Promise<Response> {
  const route = resolveBackendRoute(request.method, segments);
  if (!route) return json(404, { detail: "Not found" });

  const prepared = await prepareBody(request, route, config);
  if (prepared instanceof Response) return prepared;

  const binaryResponse = route.path.includes("/audio/");
  const headers = new Headers({ accept: binaryResponse ? "*/*" : "application/json" });
  if (prepared.contentType) headers.set("content-type", prepared.contentType);
  if (route.target === "exercises" && config.token) headers.set("authorization", `Bearer ${config.token}`);
  // Token riêng của lượt làm chỉ đi tới endpoint lượt làm, không lộ sang backend hay endpoint khác.
  const attemptToken = request.headers.get("x-attempt-token");
  if (attemptToken && route.path.startsWith("/api/attempts/")) headers.set("x-attempt-token", attemptToken);

  const fetchImpl = config.fetchImpl ?? fetch;
  try {
    // Chỉ endpoint liệt kê bài nhận query lọc và phân trang từ trình duyệt.
    const search = request.method === "GET" && route.target === "exercises" && route.path === "/api/exercises"
      ? new URL(request.url).search
      : "";
    const upstream = await fetchImpl(`${upstreamUrl(route, config)}${search}`, {
      method: request.method,
      headers,
      body: prepared.body,
      ...(prepared.duplex ? { duplex: prepared.duplex } : {}),
      signal: AbortSignal.timeout(config.timeoutMs),
      cache: "no-store",
    } as RequestInit);

    const responseHeaders = new Headers({ "content-type": upstream.headers.get("content-type") ?? "application/json" });
    const length = upstream.headers.get("content-length");
    if (length) responseHeaders.set("content-length", length);
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    const timedOut = error instanceof DOMException && (error.name === "TimeoutError" || error.name === "AbortError");
    return timedOut
      ? json(504, { error: "backend_timeout", message: "Backend phản hồi quá lâu. Thử lại sau." })
      : json(502, { error: "backend_unreachable", message: "Không kết nối được backend." });
  }
}
