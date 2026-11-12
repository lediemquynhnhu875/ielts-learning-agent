import { describe, expect, it } from "vitest";
import type { ListeningTurns } from "@/lib/api/listening";
import { blockHighlights, codePointOffsets, splitBlocks, turnBlocks } from "./blocks";

const script = "Host: Welcome to Campus Life. Today I am talking to Daniel.\nDaniel: E-sports means organised gaming.\nHost: Is it only for experts?\nDaniel: Not at all.";

/** Dựng phản hồi GET listening-turns như backend: mốc ký tự theo code point của script gốc. */
function backendTurns(text: string, list: [label: string, speech: string][]): ListeningTurns {
  const speakers: ListeningTurns["speakers"] = [];
  let from = 0;
  const turns = list.map(([label, speech], i) => {
    if (!speakers.some((s) => s.label === label)) speakers.push({ id: `speaker_${speakers.length + 1}`, label });
    const at = text.indexOf(speech, from);
    from = at + speech.length;
    const start_char = Array.from(text.slice(0, at)).length;
    return { position: i + 1, speaker_id: speakers.find((s) => s.label === label)!.id, text: speech, start_char, end_char: start_char + Array.from(speech).length };
  });
  return { speakers, turns };
}

const scriptTurns = backendTurns(script, [
  ["Host", "Welcome to Campus Life. Today I am talking to Daniel."],
  ["Daniel", "E-sports means organised gaming."],
  ["Host", "Is it only for experts?"],
  ["Daniel", "Not at all."],
]);

describe("codePointOffsets", () => {
  it("đổi chỉ số code point (Python) sang chỉ số UTF-16 (JavaScript)", () => {
    expect(codePointOffsets("a😀b")).toEqual([0, 1, 3, 4]);
    expect(codePointOffsets("")).toEqual([0]);
  });
});

describe("turnBlocks", () => {
  it("mỗi lượt nói của backend là một khối, nhãn là tên người nói, vị trí theo script gốc", () => {
    const blocks = turnBlocks(script, scriptTurns)!;
    expect(blocks.map((b) => b.label)).toEqual(["Host", "Daniel", "Host", "Daniel"]);
    expect(blocks[1].text).toBe("E-sports means organised gaming.");
    for (const b of blocks) expect(script.slice(b.start, b.start + b.text.length)).toBe(b.text);
  });

  it("phần chữ trước nhãn đầu tiên là lượt Narrator, như backend", () => {
    const text = "You will hear a talk.\nHost: Welcome.\nGuest: Hello.";
    const blocks = turnBlocks(text, backendTurns(text, [["Narrator", "You will hear a talk."], ["Host", "Welcome."], ["Guest", "Hello."]]))!;
    expect(blocks.map((b) => [b.label, b.text])).toEqual([["Narrator", "You will hear a talk."], ["Host", "Welcome."], ["Guest", "Hello."]]);
  });

  it("script có emoji và ký tự ngoài BMP: cắt theo code point, không lệch", () => {
    const text = "Host: Hi 😀 there, 𝒜lice.\nGuest: 🎧 Sure — at 8:30.";
    const turns = backendTurns(text, [["Host", "Hi 😀 there, 𝒜lice."], ["Guest", "🎧 Sure — at 8:30."]]);
    // Mốc của lượt thứ hai tính theo code point nhỏ hơn chỉ số UTF-16 đúng 2 đơn vị (hai ký tự ngoài BMP đứng trước).
    expect(turns.turns[1].start_char).toBe(text.indexOf("🎧") - 2);
    const blocks = turnBlocks(text, turns)!;
    expect(blocks.map((b) => b.text)).toEqual(["Hi 😀 there, 𝒜lice.", "🎧 Sure — at 8:30."]);
    expect(blocks[1].start).toBe(text.indexOf("🎧"));
  });

  it("lượt không khớp script (bài đã đổi sau khi tạo lượt làm) hoặc không có lượt nào thì null", () => {
    const stale = { ...scriptTurns, turns: scriptTurns.turns.map((t, i) => (i === 1 ? { ...t, text: "Something else." } : t)) };
    expect(turnBlocks(script, stale)).toBeNull();
    expect(turnBlocks("Short.", scriptTurns)).toBeNull();
    expect(turnBlocks(script, { speakers: [], turns: [] })).toBeNull();
  });
});

describe("splitBlocks", () => {
  it("Reading: chia theo dòng trống, tách nhãn [A]", () => {
    const text = "[A] Bees dance.\n\n[B] Ants follow trails.\n\nNo label here.";
    const blocks = splitBlocks(text, "reading");
    expect(blocks.map((b) => [b.label, b.text])).toEqual([["A", "Bees dance."], ["B", "Ants follow trails."], [null, "No label here."]]);
    for (const b of blocks) expect(text.slice(b.start, b.start + b.text.length)).toBe(b.text);
  });

  it("Listening: theo lượt nói của backend nếu có và khớp, không thì giữ cách chia đoạn", () => {
    expect(splitBlocks(script, "listening", scriptTurns).map((b) => b.label)).toEqual(["Host", "Daniel", "Host", "Daniel"]);
    expect(splitBlocks(script, "listening")).toHaveLength(1);
    expect(splitBlocks(script, "listening", null)).toHaveLength(1);
    expect(splitBlocks("First part.\n\nSecond part.", "listening", scriptTurns).map((b) => b.text)).toEqual(["First part.", "Second part."]);
    // Reading không dùng lượt nói.
    expect(splitBlocks(script, "reading", scriptTurns)).toHaveLength(1);
  });
});

describe("blockHighlights", () => {
  const blocks = splitBlocks(script, "listening", scriptTurns);
  const marked = (evidence: string | null) =>
    blockHighlights(blocks, script, evidence).map((r, i) => (r ? blocks[i].text.slice(r[0], r[1]) : null));

  it("bằng chứng nằm trong một lượt: chỉ tô đúng chỗ đó", () => {
    expect(marked("organised gaming")).toEqual([null, "organised gaming", null, null]);
  });

  it("bằng chứng vắt qua hai lượt: tô phần của từng lượt, không tô tên người nói", () => {
    expect(marked("organised gaming.\nHost: Is it only")).toEqual([null, "organised gaming.", "Is it only", null]);
  });

  it("không có, rỗng hoặc không nằm trong bài thì không tô", () => {
    expect(marked(null)).toEqual([null, null, null, null]);
    expect(marked("  ")).toEqual([null, null, null, null]);
    expect(marked("football")).toEqual([null, null, null, null]);
  });
});
