import type { Exercise } from "@/lib/api/types";

/** Những gì trang server cần để mở màn làm bài; nội dung bài lấy khi bắt đầu lượt làm. */
export type Playable = { id: string; skill: "reading" | "listening"; title: string };

/** Chỉ bài Reading/Listening đã kiểm chứng mới làm được; còn lại trang trả 404. */
export function toPlayable(exercise: Pick<Exercise, "id" | "skill" | "title" | "status">): Playable | null {
  if (exercise.status !== "verified" || (exercise.skill !== "reading" && exercise.skill !== "listening")) return null;
  return { id: exercise.id, skill: exercise.skill, title: exercise.title };
}
