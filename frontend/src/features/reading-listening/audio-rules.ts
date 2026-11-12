import type { AudioTurn, ExerciseAudio } from "@/lib/api/attempts";
import type { TestMode } from "./attempt-store";

/**
 * Luật trình phát Listening (ui-rules mục 5): tải trọn file trước;
 * Thi phát một lần, không tua, hết bài thì khoá; Luyện tua được, nghe lại và đếm số lần.
 */
export type AudioState = {
  /** `skipped`: Thi đã khoá từ lúc mở, không tải file. */
  load: "loading" | "ready" | "error" | "skipped";
  playing: boolean;
  plays: number;
  finished: boolean;
  /** Đã bấm Phát ít nhất một lần (lưu theo lượt làm). */
  started: boolean;
  /** Thi: tải lại trang lúc đang nghe dở, lượt nghe coi như đã dùng. */
  interrupted: boolean;
};

/** Phần lưu theo lượt làm trong attempt-store. */
export type SavedAudio = { plays: number; finished: boolean; started: boolean };

export type AudioEvent = { type: "loaded" } | { type: "failed" } | { type: "retry" } | { type: "play" } | { type: "pause" } | { type: "ended" };

export function initialAudio(saved: SavedAudio, mode: TestMode): AudioState {
  const interrupted = mode === "mock" && saved.started && !saved.finished;
  const locked = mode === "mock" && (saved.finished || interrupted);
  return { load: locked ? "skipped" : "loading", playing: false, plays: saved.plays, finished: saved.finished || interrupted, started: saved.started, interrupted };
}

export const canPlay = (mode: TestMode, state: AudioState) => state.load === "ready" && !(mode === "mock" && state.finished);

export const canSeek = (mode: TestMode) => mode === "practice";

export function audioReducer(mode: TestMode, state: AudioState, event: AudioEvent): AudioState {
  switch (event.type) {
    case "loaded":
      return { ...state, load: "ready" };
    case "failed":
      return { ...state, load: "error", playing: false };
    case "retry":
      return { ...state, load: "loading", playing: false };
    case "play":
      return canPlay(mode, state) ? { ...state, playing: true, started: true } : state;
    case "pause":
      return { ...state, playing: false };
    case "ended":
      return { ...state, playing: false, plays: state.plays + 1, finished: true };
  }
}

/** Dòng trạng thái dưới trình phát (đọc qua aria-live). */
export function audioStatus(mode: TestMode, state: AudioState): string {
  if (mode === "mock" && state.interrupted) return "Bạn đã dùng lượt nghe";
  if (mode === "mock" && state.finished) return "Bạn đã nghe hết bài";
  if (state.load === "loading") return "Đang tải audio…";
  if (state.load === "error") return "Không tải được audio";
  if (mode === "practice" && state.plays > 0) return `Đã nghe ${state.plays} lần`;
  return "";
}

const isTurn = (t: unknown): t is AudioTurn => {
  const d = t as Record<string, unknown> | null;
  return !!d && [d.start_seconds, d.end_seconds, d.source_start_char, d.source_end_char].every((v) => typeof v === "number");
};

/** Audio của bài (màn làm bài gắn vào từ GET audio/timings); không có hoặc sai hình dạng thì xem như chưa có. */
export function audioOf(exercise: { audio?: unknown }): ExerciseAudio | null {
  const audio = exercise.audio as { url?: unknown; turns?: unknown } | undefined;
  if (!audio || typeof audio.url !== "string" || !audio.url) return null;
  return { url: audio.url, turns: Array.isArray(audio.turns) ? audio.turns.filter(isTurn) : [] };
}

/**
 * Script Listening luôn thu gọn sau nút "Xem script"/"Ẩn script".
 * Có nút khi: chế độ Luyện, đã nộp bài, hoặc bài chưa có audio (lúc làm bài kèm băng báo). Thi có audio thì lúc làm bài không có script.
 */
export function scriptVisibility(mode: TestMode, hasAudio: boolean, submitted: boolean) {
  return { available: mode === "practice" || submitted || !hasAudio, noAudioNotice: !hasAudio && !submitted };
}
