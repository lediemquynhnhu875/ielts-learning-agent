"use client";

import { useEffect, useState } from "react";
import type { WritingAssessment } from "@/lib/api/writing";
import { storageGet, storageSet } from "@/lib/storage";

/**
 * Các lượt làm đã chấm của một đề (mới nhất trước), lưu trong trình duyệt để xem lại từ Kho đề.
 * Tạm thời: chưa có đăng nhập và backend Writing chưa có API lưu và lấy lại lượt làm,
 * nên chưa lưu theo tài khoản. Khi có API thì thay phần đọc/ghi này, giao diện giữ nguyên.
 */
export type SavedResult = {
  result: WritingAssessment;
  /** Bài hiển thị cùng dẫn chứng. */
  essay: string;
  /** Kết quả mẫu của Task 1 (mock). */
  sample: boolean;
  savedAt: number;
  /** Thời gian làm bài (giây), từ lúc mở đề tới lúc nộp; lượt lưu trước khi có trường này thì không có. */
  durationSec?: number;
};

/** Số lượt gần nhất giữ lại cho mỗi đề. */
export const MAX_ATTEMPTS = 5;

export const attemptsKey = (exerciseId: string) => `writing-attempts:${exerciseId}`;

const STATUSES = ["final", "provisional", "demo"];

function parseOne(value: unknown): SavedResult | null {
  if (!value || typeof value !== "object") return null;
  const data = value as Partial<SavedResult>;
  const result = data.result as Partial<WritingAssessment> | undefined;
  if (typeof data.essay !== "string" || typeof data.savedAt !== "number" || !result) return null;
  if (!STATUSES.includes(String(result.status)) || !Array.isArray(result.flags) || typeof result.word_count !== "number") return null;
  const saved: SavedResult = { result: result as WritingAssessment, essay: data.essay, sample: data.sample === true, savedAt: data.savedAt };
  if (typeof data.durationSec === "number" && data.durationSec >= 0) saved.durationSec = data.durationSec;
  return saved;
}

/** Đọc danh sách đã lưu; mục hỏng hoặc chấm lỗi bị bỏ qua. */
export function parseAttempts(raw: string | null): SavedResult[] {
  if (!raw) return [];
  try {
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data)) return [];
    return data.map(parseOne).filter((a): a is SavedResult => a !== null);
  } catch {
    return [];
  }
}

/** Thêm lượt mới lên đầu; chấm lại cùng lượt (cùng `attempt_id`) thì thay kết quả cũ; giữ tối đa MAX_ATTEMPTS. */
export function addAttempt(list: SavedResult[], next: SavedResult): SavedResult[] {
  const rest = list.filter((a) => a.result.attempt_id !== next.result.attempt_id);
  return [next, ...rest].slice(0, MAX_ATTEMPTS);
}

export function readAttempts(exerciseId: string): SavedResult[] {
  return parseAttempts(storageGet(attemptsKey(exerciseId)));
}

/** Lưu lượt vừa chấm; trả về danh sách mới. */
export function saveAttempt(exerciseId: string, next: SavedResult): SavedResult[] {
  const list = addAttempt(readAttempts(exerciseId), next);
  storageSet(attemptsKey(exerciseId), JSON.stringify(list));
  return list;
}

/** Đọc các lượt đã lưu sau khi trang gắn vào trình duyệt; `undefined` là đang đọc. */
export function useSavedAttempts(exerciseId: string | null): SavedResult[] | undefined {
  const [attempts, setAttempts] = useState<SavedResult[] | undefined>(undefined);
  useEffect(() => {
    if (!exerciseId) return;
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) setAttempts(readAttempts(exerciseId));
    });
    return () => {
      cancelled = true;
    };
  }, [exerciseId]);
  return exerciseId ? attempts : [];
}
