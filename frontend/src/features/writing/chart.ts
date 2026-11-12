/** Trục tung của biểu đồ cột: đỉnh trục và các vạch chia tròn (tối đa 5 khoảng). */
export function chartScale(values: number[]): { max: number; ticks: number[] } {
  const top = Math.max(0, ...values);
  if (top <= 0) return { max: 1, ticks: [0, 1] };

  const magnitude = 10 ** Math.floor(Math.log10(top));
  const step = [0.1, 0.2, 0.5, 1, 2, 5, 10].map((m) => m * magnitude).find((s) => Math.ceil(top / s) <= 5)!;
  const intervals = Math.ceil(top / step);
  const round = (n: number) => Number(n.toPrecision(12));
  return { max: round(intervals * step), ticks: Array.from({ length: intervals + 1 }, (_, i) => round(i * step)) };
}
