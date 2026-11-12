import { describe, expect, it } from "vitest";
import { countWords } from "@/features/writing/text";
import { exerciseCards, learnerCards } from "./exercises";
import { sampleTask1Result, writingExercises, writingTitle } from "./writing";

describe("writingTitle", () => {
  it("ghép tên thẻ và tiêu đề trang theo quyết định #8", () => {
    const task2 = writingExercises.find((e) => e.id === "wr-001")!;
    const task1 = writingExercises.find((e) => e.id === "wr-002")!;
    expect(writingTitle(task2)).toBe("Writing Task 2: Transport");
    expect(writingTitle(task1)).toBe("Writing Task 1: Tourism");
  });

  it("thẻ Writing ở Kho đề dùng cùng tên", () => {
    expect(exerciseCards.find((c) => c.id === "wr-001")?.title).toBe("Writing Task 2: Transport");
  });
});

describe("đề Task 1 (Tourism)", () => {
  const task1 = writingExercises.find((e) => e.id === "wr-002")!;

  it("có số liệu biểu đồ: mỗi chuỗi có đủ giá trị cho mọi mốc", () => {
    expect(task1.chart).toBeDefined();
    const chart = task1.chart!;
    expect(chart.categories).toEqual(["2021", "2022", "2023", "2024"]);
    for (const series of chart.series) expect(series.values).toHaveLength(chart.categories.length);
  });

  it("người học thấy được thẻ Task 1 để vào màn viết", () => {
    expect(learnerCards("writing").map((c) => c.id)).toContain("wr-002");
  });
});

describe("kết quả mẫu Task 1", () => {
  it("dẫn chứng và lỗi trỏ đúng vị trí trong bài mẫu (code point)", () => {
    const { essay, result } = sampleTask1Result;
    const chars = Array.from(essay);
    for (const row of result.criteria ?? []) {
      for (const ev of row.evidence) expect(chars.slice(ev.start_char, ev.end_char).join("")).toBe(ev.quote);
    }
    for (const c of result.corrections ?? []) expect(essay).toContain(c.quote);
  });

  it("số từ khớp cách đếm của backend", () => {
    expect(sampleTask1Result.result.word_count).toBe(countWords(sampleTask1Result.essay));
  });
});
