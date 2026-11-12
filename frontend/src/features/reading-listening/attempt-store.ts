import { isUuid } from "@/lib/backend/proxy-rules";
import { storageGet, storageSet } from "@/lib/storage";

/**
 * Các lượt làm Reading/Listening của một bài (mới nhất trước), lưu trong trình duyệt.
 * Token chỉ trả một lần lúc tạo lượt, mất là không mở lại được lượt đó.
 * Tạm thời: chưa có đăng nhập nên lượt gắn với trình duyệt, không gắn với tài khoản.
 */
export type TestMode = "practice" | "mock";

export type StoredAttempt = {
  attemptId: string;
  token: string;
  /** Số lần nghe hết bài (Listening). */
  plays: number;
  /** Chế độ Thi: đã nghe hết, khoá trình phát. */
  finished: boolean;
  /** Chế độ Thi: đã bấm Phát; tải lại lúc đang nghe dở thì khoá. */
  started: boolean;
  /** Đã nộp (theo lần mở gần nhất trên trình duyệt này); để mở lại không phải hỏi backend từng lượt. */
  submitted: boolean;
  /** Số câu đúng trên tổng ("7/10") của lượt đã nộp, cho hàng chọn lượt; lượt lưu trước khi có trường này thì không có. */
  score?: string;
  savedAt: number;
};

export const MAX_ATTEMPTS = 5;

export const attemptsKey = (mode: TestMode, exerciseId: string) => `rl-attempts:${mode}:${exerciseId}`;

function parseOne(value: unknown): StoredAttempt | null {
  if (!value || typeof value !== "object") return null;
  const d = value as Record<string, unknown>;
  if (typeof d.attemptId !== "string" || !isUuid(d.attemptId)) return null;
  // Backend nhận token tối đa 256 ký tự.
  if (typeof d.token !== "string" || !d.token || d.token.length > 256) return null;
  if (!Number.isInteger(d.plays) || (d.plays as number) < 0 || typeof d.finished !== "boolean" || typeof d.savedAt !== "number") return null;
  // Lượt lưu trước khi có hai cờ này thì không có trường; có mà sai kiểu là mục hỏng.
  const flag = (value: unknown) => (value === undefined ? false : typeof value === "boolean" ? value : null);
  const started = flag(d.started);
  const submitted = flag(d.submitted);
  if (started === null || submitted === null) return null;
  const stored: StoredAttempt = { attemptId: d.attemptId, token: d.token, plays: d.plays as number, finished: d.finished, started, submitted, savedAt: d.savedAt };
  if (typeof d.score === "string" && d.score.length <= 12) stored.score = d.score;
  return stored;
}

export function parseAttempts(raw: string | null): StoredAttempt[] {
  if (!raw) return [];
  try {
    const data: unknown = JSON.parse(raw);
    return Array.isArray(data) ? data.map(parseOne).filter((a): a is StoredAttempt => a !== null) : [];
  } catch {
    return [];
  }
}

export function addAttempt(list: StoredAttempt[], next: StoredAttempt): StoredAttempt[] {
  return [next, ...list.filter((a) => a.attemptId !== next.attemptId)].slice(0, MAX_ATTEMPTS);
}

export function updateAttempt(
  list: StoredAttempt[],
  attemptId: string,
  patch: Partial<Pick<StoredAttempt, "plays" | "finished" | "started" | "submitted" | "score">>,
): StoredAttempt[] {
  return list.map((a) => (a.attemptId === attemptId ? { ...a, ...patch } : a));
}

/**
 * Lượt cần mở khi vào màn làm bài; `null` là tạo lượt mới.
 * Thường: lượt chưa nộp mới nhất. `?view=result`: lượt đã nộp mới nhất, không có thì lượt chưa nộp. `?redo=1`: luôn tạo mới.
 */
export function pickAttempt(list: StoredAttempt[], { redo, wantResult }: { redo: boolean; wantResult: boolean }): StoredAttempt | null {
  if (redo) return null;
  const open = list.find((a) => !a.submitted) ?? null;
  return wantResult ? (list.find((a) => a.submitted) ?? open) : open;
}

export function removeAttempt(list: StoredAttempt[], attemptId: string): StoredAttempt[] {
  return list.filter((a) => a.attemptId !== attemptId);
}

export function readAttempts(mode: TestMode, exerciseId: string): StoredAttempt[] {
  return parseAttempts(storageGet(attemptsKey(mode, exerciseId)));
}

export function writeAttempts(mode: TestMode, exerciseId: string, list: StoredAttempt[]): void {
  storageSet(attemptsKey(mode, exerciseId), JSON.stringify(list));
}
