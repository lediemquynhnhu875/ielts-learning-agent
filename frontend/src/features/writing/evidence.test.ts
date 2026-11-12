import { describe, expect, it } from "vitest";
import { segmentEssay } from "./evidence";

describe("segmentEssay", () => {
  it("không có dẫn chứng thì trả nguyên bài một đoạn", () => {
    expect(segmentEssay("Hello world", [])).toEqual([{ text: "Hello world", start: 0, criteria: [] }]);
  });

  it("cắt bài theo vị trí dẫn chứng", () => {
    const segs = segmentEssay("Hello big world", [{ criterion: "LR", start: 6, end: 9 }]);
    expect(segs).toEqual([
      { text: "Hello ", start: 0, criteria: [] },
      { text: "big", start: 6, criteria: ["LR"] },
      { text: " world", start: 9, criteria: [] },
    ]);
  });

  it("vị trí tính theo code point như Python, không theo UTF-16", () => {
    // "😀" là 1 code point nhưng 2 đơn vị UTF-16.
    const text = "A 😀 smile here";
    const segs = segmentEssay(text, [{ criterion: "TR", start: 4, end: 9 }]);
    expect(segs.map((s) => s.text)).toEqual(["A 😀 ", "smile", " here"]);
  });

  it("hai dẫn chứng chồng nhau chia thành đoạn mang cả hai tiêu chí", () => {
    const segs = segmentEssay("abcdefgh", [
      { criterion: "TR", start: 1, end: 5 },
      { criterion: "GRA", start: 3, end: 7 },
    ]);
    expect(segs).toEqual([
      { text: "a", start: 0, criteria: [] },
      { text: "bc", start: 1, criteria: ["TR"] },
      { text: "de", start: 3, criteria: ["TR", "GRA"] },
      { text: "fg", start: 5, criteria: ["GRA"] },
      { text: "h", start: 7, criteria: [] },
    ]);
  });

  it("bỏ qua dẫn chứng có vị trí sai hoặc nằm ngoài bài", () => {
    const segs = segmentEssay("abc", [
      { criterion: "TR", start: 2, end: 1 },
      { criterion: "CC", start: -1, end: 2 },
      { criterion: "LR", start: 1, end: 99 },
    ]);
    expect(segs).toEqual([{ text: "abc", start: 0, criteria: [] }]);
  });
});
