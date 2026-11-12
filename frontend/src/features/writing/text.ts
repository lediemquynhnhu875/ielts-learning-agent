/** Cùng regex đếm từ với backend Writing (`prototypes/writing/app.py`, `count_words`). */
const WORD = /[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g;

export function countWords(text: string): number {
  return text.match(WORD)?.length ?? 0;
}

/** Tỉ lệ số từ so với tối thiểu cho thanh tiến độ (0–1). */
export function wordRatio(words: number, minWords: number): number {
  return Math.min(1, words / minWords);
}

/** Số giây còn lại, tính từ lúc bắt đầu (ms) nên tải lại trang vẫn đúng. */
export function remainingSeconds(startedAt: number, now: number, minutes: number): number {
  return Math.max(0, Math.ceil((startedAt + minutes * 60_000 - now) / 1000));
}

export function formatClock(seconds: number): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`;
}

/** Thời gian làm bài hiển thị dưới tiêu đề màn kết quả. */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return "Làm trong dưới 1 phút";
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `Làm trong ${minutes} phút`;
  return `Làm trong ${Math.floor(minutes / 60)} giờ ${minutes % 60} phút`;
}
