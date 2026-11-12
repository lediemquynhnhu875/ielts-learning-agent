/** Nháp bài viết lưu trong trình duyệt: tải lại trang không mất chữ, đồng hồ tính tiếp từ lúc bắt đầu. */
export type WritingDraft = {
  text: string;
  /** Lúc bắt đầu làm bài (ms). */
  startedAt: number;
  /** Lần lưu nháp gần nhất (ms); `null` khi chưa gõ gì. */
  savedAt: number | null;
  /** Mã lượt làm bài gửi kèm khi chấm; giữ nguyên khi chấm lại. */
  attemptId: string;
};

export const draftKey = (exerciseId: string) => `writing-draft:${exerciseId}`;

const newAttemptId = () =>
  `att_${typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID().replaceAll("-", "") : Date.now().toString(36)}`;

/** Đọc nháp đã lưu; không có hoặc hỏng thì bắt đầu nháp mới tính giờ từ `now`. */
export function parseDraft(raw: string | null, now: number): WritingDraft {
  const fresh: WritingDraft = { text: "", startedAt: now, savedAt: null, attemptId: newAttemptId() };
  if (!raw) return fresh;
  try {
    const data = JSON.parse(raw) as Partial<WritingDraft>;
    if (typeof data.text !== "string" || typeof data.startedAt !== "number") return fresh;
    return {
      text: data.text,
      startedAt: data.startedAt,
      savedAt: typeof data.savedAt === "number" ? data.savedAt : null,
      attemptId: typeof data.attemptId === "string" && data.attemptId ? data.attemptId : fresh.attemptId,
    };
  } catch {
    return fresh;
  }
}
