import { forwardToBackend } from "@/lib/backend/forward";
import { backendConfig } from "@/lib/backend/server-fetch";

/**
 * Route trung gian tới backend UC-04, Speaking và Writing (các backend không bật CORS).
 * Địa chỉ backend và API_TOKEN chỉ đọc phía server, không có tiền tố NEXT_PUBLIC_ (xem backendConfig).
 * Sinh bài, chấm bài có thể mất vài chục giây đến vài phút: chờ tối đa 300 giây (5 phút).
 */
export const maxDuration = 300;

export async function GET(request: Request, ctx: RouteContext<"/api/backend/[...path]">) {
  const { path } = await ctx.params;
  return forwardToBackend(request, path, backendConfig());
}

export async function POST(request: Request, ctx: RouteContext<"/api/backend/[...path]">) {
  const { path } = await ctx.params;
  return forwardToBackend(request, path, backendConfig());
}

/** Lưu nháp lượt làm Reading/Listening (PATCH attempts/{id}/answers). */
export async function PATCH(request: Request, ctx: RouteContext<"/api/backend/[...path]">) {
  const { path } = await ctx.params;
  return forwardToBackend(request, path, backendConfig());
}
