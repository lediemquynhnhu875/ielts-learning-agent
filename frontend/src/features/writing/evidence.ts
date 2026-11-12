/** Một dẫn chứng trong bài: vị trí theo code point (backend Python cắt chuỗi theo code point). */
export type EvidenceSpan = { criterion: string; start: number; end: number };

/** Một đoạn bài liền nhau có cùng tập tiêu chí dẫn chứng; `start` là vị trí code point. */
export type EssaySegment = { text: string; start: number; criteria: string[] };

/**
 * Cắt bài thành các đoạn để tô dẫn chứng. Dùng `Array.from` để đếm theo code point,
 * không theo đơn vị UTF-16 của JavaScript (emoji, ký tự ngoài BMP). Dẫn chứng sai vị trí bị bỏ qua.
 */
export function segmentEssay(text: string, spans: EvidenceSpan[]): EssaySegment[] {
  const chars = Array.from(text);
  const valid = spans.filter((s) => Number.isInteger(s.start) && Number.isInteger(s.end) && s.start >= 0 && s.end > s.start && s.end <= chars.length);

  const cuts = new Set([0, chars.length]);
  for (const s of valid) {
    cuts.add(s.start);
    cuts.add(s.end);
  }
  const points = [...cuts].sort((a, b) => a - b);

  const segments: EssaySegment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [from, to] = [points[i], points[i + 1]];
    const criteria: string[] = [];
    for (const s of valid) if (s.start <= from && s.end >= to && !criteria.includes(s.criterion)) criteria.push(s.criterion);
    segments.push({ text: chars.slice(from, to).join(""), start: from, criteria });
  }
  return segments;
}
