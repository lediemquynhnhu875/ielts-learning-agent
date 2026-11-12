import { forwardToBackend, type ForwardConfig } from "./forward";

const PREFIX = /^\/api\/backend\/?/;

/** Cấu hình backend đọc từ biến môi trường phía server (không có tiền tố NEXT_PUBLIC_). */
export function backendConfig(): ForwardConfig {
  return {
    backendUrl: process.env.BACKEND_URL || "http://127.0.0.1:8000",
    token: process.env.API_TOKEN ?? "",
    speakingUrl: process.env.SPEAKING_BACKEND_URL || "http://127.0.0.1:8010",
    writingUrl: process.env.WRITING_BACKEND_URL || "http://127.0.0.1:8765",
    // Chỉ đúng chữ "demo" mới bật chế độ mô phỏng; mọi giá trị khác là chấm thật.
    writingMode: process.env.WRITING_MODE === "demo" ? "demo" : "live",
    timeoutMs: 300_000,
  };
}

/**
 * `fetch` cho server component: nhận cùng đường dẫn `/api/backend/...` như client trên trình duyệt
 * nhưng gọi thẳng backend, đi qua đúng danh sách cho phép và xử lý lỗi của route trung gian.
 */
export function createServerFetch(config: ForwardConfig = backendConfig()): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(String(input), "http://internal");
    const segments = url.pathname.replace(PREFIX, "").split("/").filter(Boolean);
    return forwardToBackend(new Request(url, init), segments, config);
  }) as typeof fetch;
}
