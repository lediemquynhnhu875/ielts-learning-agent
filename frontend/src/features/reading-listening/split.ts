/** Tỉ lệ bề rộng cột trái (bài đọc/script) của màn làm bài và màn kết quả. */
export const DEFAULT_RATIO = 0.54;
export const MIN_COLUMN = 360;
/** Phần không chia theo tỉ lệ: khe chứa nút kéo 32px, 12px đệm mỗi bên và 6px thanh cuộn của mỗi cột. */
export const GUTTER = 68;

/** Tỉ lệ nhỏ nhất và lớn nhất để mỗi cột còn ít nhất 360px; chưa đo được bề rộng thì 0–1. */
export function splitBounds(width: number): [number, number] {
  if (width <= 0) return [0, 1];
  const usable = width - GUTTER;
  if (usable < 2 * MIN_COLUMN) return [0.5, 0.5];
  const low = MIN_COLUMN / usable;
  return [low, 1 - low];
}

/** Kẹp tỉ lệ vào giới hạn của vùng chứa; giá trị hỏng (đọc từ localStorage) về mặc định. */
export function clampRatio(ratio: number, width: number): number {
  if (!Number.isFinite(ratio)) return DEFAULT_RATIO;
  const [low, high] = splitBounds(width);
  return Math.min(high, Math.max(low, ratio));
}
