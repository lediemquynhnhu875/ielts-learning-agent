import type { AnswerMap } from "@/lib/api/attempts";

/** `pending`: có thay đổi đang chờ hết 1 giây ngưng thao tác. */
export type SaveStatus = "pending" | "saving" | "saved" | "error";

/** Backend nhận tối đa 40 câu mỗi request. */
export const MAX_PER_REQUEST = 40;

type DraftOptions = {
  save: (answers: AnswerMap) => Promise<unknown>;
  onStatus: (status: SaveStatus, error?: unknown) => void;
  delayMs?: number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
};

/**
 * Tự lưu đáp án: gom thay đổi, gửi PATCH sau `delayMs` ngưng thao tác, tối đa 40 câu mỗi lần.
 * Lỗi thì giữ thay đổi để Thử lại; thay đổi mới hơn của cùng câu không bị ghi đè.
 * Đồng hồ truyền vào được để test không phải chờ thật.
 */
export function createAnswerDraft({
  save,
  onStatus,
  delayMs = 1000,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
}: DraftOptions) {
  const pending = new Map<string, string | null>();
  let timer: unknown = null;
  let running: Promise<boolean> | null = null;
  let closed = false;

  const report = (status: SaveStatus, error?: unknown) => {
    if (!closed) onStatus(status, error);
  };

  function stopTimer() {
    if (timer !== null) clearTimer(timer);
    timer = null;
  }

  async function drain(): Promise<boolean> {
    // Dừng khi có hẹn giờ mới: thay đổi trong lúc đang lưu đợi người học ngưng thao tác.
    while (!closed && pending.size > 0 && timer === null) {
      const batch = Object.fromEntries([...pending].slice(0, MAX_PER_REQUEST));
      for (const key of Object.keys(batch)) pending.delete(key);
      report("saving");
      try {
        await save(batch);
      } catch (error) {
        for (const [key, value] of Object.entries(batch)) if (!pending.has(key)) pending.set(key, value);
        report("error", error);
        return false;
      }
    }
    report(pending.size > 0 ? "pending" : "saved");
    return true;
  }

  function flush(): Promise<boolean> {
    stopTimer();
    running ??= drain().finally(() => {
      running = null;
    });
    return running;
  }

  return {
    change(questionId: string, value: string) {
      if (closed) return;
      pending.set(questionId, value.trim() ? value : null);
      stopTimer();
      timer = setTimer(() => {
        timer = null;
        void flush();
      }, delayMs);
      report("pending");
    },
    flush,
    retry: flush,
    /** Nộp bài: bỏ hẹn giờ và thay đổi chưa gửi (nộp gửi toàn bộ đáp án), không báo trạng thái nữa. */
    close() {
      closed = true;
      stopTimer();
      pending.clear();
    },
  };
}

export type AnswerDraft = ReturnType<typeof createAnswerDraft>;
