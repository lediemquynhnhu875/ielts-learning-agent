import type { ListeningTurns } from "@/lib/api/listening";
import { PARAGRAPH_LABEL } from "./paragraph";

/** Một khối hiển thị của bài đọc/script: đoạn văn (nhãn A, B…) hoặc lượt nói (tên người nói). `start` là vị trí của `text` trong bài gốc. */
export type Block = { label: string | null; text: string; start: number };

/**
 * Chỉ số UTF-16 của từng code point: `offsets[i]` là vị trí trong chuỗi JavaScript của ký tự thứ i tính theo code point.
 * Backend (Python) đánh mốc ký tự theo code point, JavaScript theo UTF-16; hai cách lệch nhau khi có emoji hay ký tự ngoài BMP.
 */
export function codePointOffsets(text: string): number[] {
  const offsets = [0];
  for (const char of text) offsets.push(offsets[offsets.length - 1] + char.length);
  return offsets;
}

/**
 * Khối theo lượt người nói của backend (GET exercises/{id}/listening-turns): mỗi lượt một khối, nhãn là tên người nói;
 * phần chữ trước nhãn đầu tiên là lượt "Narrator". `null` nếu không có lượt nào hoặc có lượt không khớp script
 * (bản chụp bài của lượt làm khác bài hiện tại), để nơi gọi chia theo đoạn.
 */
export function turnBlocks(text: string, data: ListeningTurns): Block[] | null {
  if (data.turns.length === 0) return null;
  const offsets = codePointOffsets(text);
  const labels = new Map(data.speakers.map((s) => [s.id, s.label]));
  const blocks: Block[] = [];
  for (const turn of data.turns) {
    const start = offsets[turn.start_char];
    if (start === undefined || text.slice(start, offsets[turn.end_char]) !== turn.text) return null;
    blocks.push({ label: labels.get(turn.speaker_id) ?? null, text: turn.text, start });
  }
  return blocks;
}

/** Đoạn văn tách bằng dòng trống (như `splitParagraphs`), nhãn [A] tách riêng. */
function paragraphBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let position = 0;
  // Nhóm bắt giữ lại phần ngăn cách để tính đúng vị trí.
  text.split(/(\n\s*\n)/).forEach((part, i) => {
    if (i % 2 === 0 && part) {
      const label = part.match(PARAGRAPH_LABEL);
      const skip = label ? label[0].length : 0;
      blocks.push({ label: label ? label[1] : null, text: part.slice(skip), start: position + skip });
    }
    position += part.length;
  });
  return blocks;
}

/** Khối hiển thị của bài: Listening theo lượt người nói của backend nếu có và khớp script, còn lại theo đoạn văn. */
export function splitBlocks(text: string, skill: "reading" | "listening", turns?: ListeningTurns | null): Block[] {
  return (skill === "listening" && turns ? turnBlocks(text, turns) : null) ?? paragraphBlocks(text);
}

/**
 * Phần cần tô của từng khối (vị trí trong `text` của khối), `null` là không tô.
 * Bằng chứng là chuỗi trích nguyên văn từ bài; vắt qua nhiều khối thì mỗi khối tô phần của mình.
 */
export function blockHighlights(blocks: Block[], text: string, evidence: string | null): ([number, number] | null)[] {
  const from = evidence?.trim() ? text.indexOf(evidence) : -1;
  if (from < 0 || !evidence) return blocks.map(() => null);
  const to = from + evidence.length;
  return blocks.map((block) => {
    const start = Math.max(from, block.start) - block.start;
    const end = Math.min(to, block.start + block.text.length) - block.start;
    return end > start && block.text.slice(start, end).trim() ? [start, end] : null;
  });
}
