/**
 * Kiểu dữ liệu dùng chung cho Kho đề, bám theo `CONTENT_ITEM` trong
 * DATABASE_CONTEXT.md và các hợp đồng UC-04 (`backend/ielts_agent/agents/uc04/models.py`).
 */

export type Skill = "reading" | "listening" | "writing" | "speaking";

/** Chưa có nghĩa chính thức cho `spare`/`rejected`; nhóm sẽ chốt sau (xem handoff). */
export type ExerciseStatus = "verified" | "spare" | "rejected";

export type Source = "self_written" | "llm_generated_verified" | "open_license";

export const skillLabel: Record<Skill, string> = {
  reading: "Reading",
  listening: "Listening",
  writing: "Writing",
  speaking: "Speaking",
};

/** Màu nhận diện kỹ năng (token Tailwind trong globals.css). */
export const skillColorClass: Record<Skill, string> = {
  reading: "bg-skill-reading",
  listening: "bg-skill-listening",
  writing: "bg-skill-writing",
  speaking: "bg-skill-speaking",
};

export const statusLabel: Record<ExerciseStatus, string> = {
  verified: "Xác nhận",
  spare: "Dự phòng",
  rejected: "Đã loại",
};

/** Thông tin một mục trong `CONTENT_ITEM`, phần chung cho cả 4 kỹ năng. */
export type ContentItemBase = {
  id: string;
  skill: Skill;
  topic: string;
  /** `null` cho Speaking: dữ liệu mẫu hiện có không ghi target_band. */
  targetBand: number | null;
  source: Source;
  status: ExerciseStatus;
  /** `null` khi không phải do model sinh (ví dụ self_written). */
  model: string | null;
  promptVersion: string | null;
  createdAt: string;
  /** Số câu bị báo sai đang chờ xử lý trên bài này (chip chỉ quản trị). BE chưa có endpoint báo sai. */
  reportCount: number;
};
