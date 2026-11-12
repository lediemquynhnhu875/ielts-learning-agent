import { notFound } from "next/navigation";
import { getExercise } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { isUuid } from "@/lib/backend/proxy-rules";
import { createServerFetch } from "@/lib/backend/server-fetch";
import { toPlayable, type Playable } from "./playable";

/**
 * Trang server của màn làm bài: đọc bài phía server (token không ra trình duyệt).
 * Id không phải UUID, bài không có, chưa kiểm chứng hoặc không phải Reading/Listening thì 404.
 * Lỗi khác (backend tắt, CSDL chưa sẵn sàng) trả thông điệp để trang hiện.
 */
export async function loadPlayable(id: string): Promise<Playable | { error: string }> {
  if (!isUuid(id)) notFound();
  let exercise;
  try {
    exercise = await getExercise(id, createServerFetch());
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return { error: error instanceof ApiError ? error.message : "Lỗi không xác định." };
  }
  return toPlayable(exercise) ?? notFound();
}
