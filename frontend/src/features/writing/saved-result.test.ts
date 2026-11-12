import { describe, expect, it } from "vitest";
import type { WritingAssessment } from "@/lib/api/writing";
import { sampleTask1Result } from "@/mock-data/writing";
import { MAX_ATTEMPTS, addAttempt, attemptsKey, parseAttempts, type SavedResult } from "./saved-result";

function attempt(id: string, savedAt: number, overall = 6): SavedResult {
  const result: WritingAssessment = { ...sampleTask1Result.result, attempt_id: id, overall_band: overall };
  return { result, essay: sampleTask1Result.essay, sample: false, savedAt };
}

describe("attemptsKey", () => {
  it("mỗi đề một khoá riêng, tách khỏi khoá nháp", () => {
    expect(attemptsKey("wr-001")).toBe("writing-attempts:wr-001");
  });
});

describe("addAttempt", () => {
  it("lượt mới nằm đầu danh sách", () => {
    const list = addAttempt([attempt("att_1", 1)], attempt("att_2", 2));
    expect(list.map((a) => a.result.attempt_id)).toEqual(["att_2", "att_1"]);
  });

  it(`chỉ giữ ${MAX_ATTEMPTS} lượt gần nhất`, () => {
    let list: SavedResult[] = [];
    for (let i = 1; i <= MAX_ATTEMPTS + 2; i++) list = addAttempt(list, attempt(`att_${i}`, i));
    expect(list).toHaveLength(MAX_ATTEMPTS);
    expect(list[0].result.attempt_id).toBe(`att_${MAX_ATTEMPTS + 2}`);
    expect(list.at(-1)?.result.attempt_id).toBe("att_3");
  });

  it("chấm lại cùng một lượt (cùng attempt_id) thì thay kết quả cũ, không thêm lượt", () => {
    const list = addAttempt([attempt("att_1", 1, 6), attempt("att_0", 0)], attempt("att_1", 5, 6.5));
    expect(list).toHaveLength(2);
    expect(list[0]).toMatchObject({ savedAt: 5, result: { attempt_id: "att_1", overall_band: 6.5 } });
  });
});

describe("parseAttempts", () => {
  it("đọc lại đúng danh sách đã lưu", () => {
    const list = [attempt("att_2", 2), attempt("att_1", 1)];
    expect(parseAttempts(JSON.stringify(list))).toEqual(list);
  });

  it("chưa có hoặc dữ liệu hỏng thì là danh sách rỗng", () => {
    expect(parseAttempts(null)).toEqual([]);
    expect(parseAttempts("{hỏng")).toEqual([]);
    expect(parseAttempts(JSON.stringify({ essay: "x" }))).toEqual([]);
  });

  it("bỏ mục hỏng và kết quả chấm lỗi, giữ mục hợp lệ", () => {
    const good = attempt("att_1", 1);
    const failed = { ...attempt("att_2", 2), result: { ...good.result, status: "failed" } };
    expect(parseAttempts(JSON.stringify([failed, { essay: 1 }, good]))).toEqual([good]);
  });

  it("giữ thời gian làm bài nếu có, bỏ giá trị không hợp lệ", () => {
    const timed = { ...attempt("att_1", 1), durationSec: 1440 };
    const bad = { ...attempt("att_2", 2), durationSec: "lâu" };
    expect(parseAttempts(JSON.stringify([timed, bad]))).toEqual([timed, attempt("att_2", 2)]);
  });
});
