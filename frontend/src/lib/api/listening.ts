/**
 * Client cho dữ liệu Listening của #35 (docs/listening-speaker-turns.md, docs/listening-azure-speech.md), gọi qua route trung gian.
 * Mốc ký tự của backend (`start_char`, `source_start_char`…) là chỉ số code point theo Python trong script gốc,
 * cuối không bao gồm; khi cắt chuỗi trong JavaScript phải quy đổi (xem `codePointOffsets` ở features/reading-listening/blocks.ts).
 */
import type { AudioTurn, ExerciseAudio } from "./attempts";
import { BASE, request } from "./client";

/** Phản hồi của GET /api/exercises/{id}/listening-turns. Phần chữ trước nhãn đầu tiên thuộc người nói "Narrator". */
export type ListeningTurns = {
  speakers: { id: string; label: string }[];
  turns: { position: number; speaker_id: string; text: string; start_char: number; end_char: number }[];
};

/** Phản hồi của GET /api/exercises/{id}/audio/timings; chỉ có khi audio đã qua kiểm chứng. */
export type AudioTimings = {
  item_id: string;
  audio_sha256: string;
  sample_rate: number;
  turns: (AudioTurn & { position: number; speaker_id: string; start_frame: number; end_frame: number })[];
};

/** Lượt người nói và audio của một bài Listening; `null` là không có (màn làm bài rơi về "chưa có audio", script chia theo đoạn). */
export type ListeningExtras = { audio: ExerciseAudio | null; turns: ListeningTurns | null };

/** WAV đã kiểm chứng, tải qua route trung gian (token không ra trình duyệt). */
export const audioUrl = (exerciseId: string) => `${BASE}/exercises/${exerciseId}/audio`;

export function getListeningTurns(exerciseId: string, fetchImpl: typeof fetch = fetch) {
  return request<ListeningTurns>(`/exercises/${exerciseId}/listening-turns`, { method: "GET" }, fetchImpl);
}

export function getAudioTimings(exerciseId: string, fetchImpl: typeof fetch = fetch) {
  return request<AudioTimings>(`/exercises/${exerciseId}/audio/timings`, { method: "GET" }, fetchImpl);
}

const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

function validTurns(data: ListeningTurns): ListeningTurns | null {
  const ok =
    Array.isArray(data?.speakers) &&
    Array.isArray(data?.turns) &&
    data.speakers.every((s) => typeof s?.id === "string" && typeof s?.label === "string") &&
    data.turns.every((t) => typeof t?.text === "string" && typeof t?.speaker_id === "string" && isNumber(t.start_char) && isNumber(t.end_char));
  return ok ? data : null;
}

function toAudio(exerciseId: string, data: AudioTimings): ExerciseAudio | null {
  if (!Array.isArray(data?.turns)) return null;
  const turns = data.turns
    .filter((t) => isNumber(t?.start_seconds) && isNumber(t?.end_seconds) && isNumber(t?.source_start_char) && isNumber(t?.source_end_char))
    .map(({ start_seconds, end_seconds, source_start_char, source_end_char }) => ({ start_seconds, end_seconds, source_start_char, source_end_char }));
  return { url: audioUrl(exerciseId), turns };
}

/**
 * Lấy lượt người nói và audio đã kiểm chứng của bài Listening (GET attempts/{id} chưa có hai phần này).
 * Không ném lỗi: 409 `audio_not_verified`, 404, lỗi mạng hay phản hồi sai hình dạng đều coi như không có,
 * để màn làm bài dùng trạng thái "chưa có audio" sẵn có thay vì báo lỗi.
 */
export async function loadListeningExtras(exerciseId: string, fetchImpl: typeof fetch = fetch): Promise<ListeningExtras> {
  const [turns, audio] = await Promise.all([
    getListeningTurns(exerciseId, fetchImpl).then(validTurns, () => null),
    getAudioTimings(exerciseId, fetchImpl).then((timings) => toAudio(exerciseId, timings), () => null),
  ]);
  return { audio, turns };
}
