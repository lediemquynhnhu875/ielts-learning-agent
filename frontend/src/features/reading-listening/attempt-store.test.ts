import { describe, expect, it } from "vitest";
import { addAttempt, attemptsKey, MAX_ATTEMPTS, parseAttempts, pickAttempt, removeAttempt, updateAttempt, type StoredAttempt } from "./attempt-store";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";
const ID2 = "9c1e4f52-7a3b-4d6e-8f10-a2b3c4d5e6f7";
const one: StoredAttempt = { attemptId: ID, token: "tok", plays: 0, finished: false, started: false, submitted: false, savedAt: 1 };
const uuid = (i: number) => `${ID.slice(0, -2)}${String(i).padStart(2, "0")}`;

describe("attemptsKey", () => {
  it("tách theo chế độ và bài", () => {
    expect(attemptsKey("practice", "x")).toBe("rl-attempts:practice:x");
    expect(attemptsKey("mock", "x")).toBe("rl-attempts:mock:x");
  });
});

describe("parseAttempts", () => {
  it("đọc mục hợp lệ, bỏ trường thừa", () => {
    expect(parseAttempts(JSON.stringify([{ ...one, extra: 1 }]))).toEqual([one]);
  });

  it("lượt lưu trước khi có cờ started, submitted thì coi là false", () => {
    const old: Partial<StoredAttempt> = { ...one };
    delete old.started;
    delete old.submitted;
    expect(parseAttempts(JSON.stringify([old]))).toEqual([one]);
    const flagged = { ...one, started: true, submitted: true };
    expect(parseAttempts(JSON.stringify([flagged]))).toEqual([flagged]);
  });

  it("giữ điểm đã lưu của lượt đã nộp; điểm sai kiểu thì bỏ điểm, vẫn giữ lượt", () => {
    const scored = { ...one, submitted: true, score: "7/10" };
    expect(parseAttempts(JSON.stringify([scored]))).toEqual([scored]);
    expect(parseAttempts(JSON.stringify([{ ...one, score: 7 }]))).toEqual([one]);
    expect(parseAttempts(JSON.stringify([{ ...one, score: "x".repeat(20) }]))).toEqual([one]);
  });

  it("rỗng, JSON hỏng, không phải mảng thì trả rỗng", () => {
    expect(parseAttempts(null)).toEqual([]);
    expect(parseAttempts("{")).toEqual([]);
    expect(parseAttempts("{}")).toEqual([]);
  });

  it("bỏ mục hỏng: id không phải UUID, thiếu token, số lần nghe sai, cờ sai", () => {
    const raw = JSON.stringify([
      { ...one, attemptId: "abc" },
      { ...one, token: "" },
      { ...one, plays: -1 },
      { ...one, plays: 1.5 },
      { ...one, finished: "yes" },
      { ...one, started: "yes" },
      { ...one, savedAt: "1" },
      { ...one, attemptId: ID2, plays: 2, finished: true },
    ]);
    expect(parseAttempts(raw)).toEqual([{ ...one, attemptId: ID2, plays: 2, finished: true }]);
  });
});

describe("addAttempt, updateAttempt, removeAttempt", () => {
  it("thêm lên đầu, trùng id thì thay, giữ tối đa 5 lượt", () => {
    const many = Array.from({ length: MAX_ATTEMPTS }, (_, i) => ({ ...one, attemptId: uuid(i) }));
    const next = addAttempt(many, { ...one, attemptId: ID2 });
    expect(MAX_ATTEMPTS).toBe(5);
    expect(next).toHaveLength(5);
    expect(next[0].attemptId).toBe(ID2);
    expect(next.map((a) => a.attemptId)).not.toContain(uuid(4));
    expect(addAttempt([one], { ...one, token: "mới" })).toEqual([{ ...one, token: "mới" }]);
  });

  it("cập nhật số lần nghe và cờ nghe hết của đúng lượt, giữ thứ tự", () => {
    const list = [one, { ...one, attemptId: ID2 }];
    expect(updateAttempt(list, ID2, { plays: 1, finished: true })).toEqual([one, { ...one, attemptId: ID2, plays: 1, finished: true }]);
    expect(updateAttempt(list, uuid(9), { plays: 3 })).toEqual(list);
  });

  it("cập nhật cờ đã bắt đầu nghe và đã nộp", () => {
    expect(updateAttempt([one], ID, { started: true, submitted: true })).toEqual([{ ...one, started: true, submitted: true }]);
    expect(updateAttempt([one], ID, { submitted: true, score: "7/10" })).toEqual([{ ...one, submitted: true, score: "7/10" }]);
  });

  it("bỏ lượt theo id", () => {
    expect(removeAttempt([one, { ...one, attemptId: ID2 }], ID)).toEqual([{ ...one, attemptId: ID2 }]);
  });
});

describe("pickAttempt", () => {
  const done = { ...one, attemptId: ID2, submitted: true };

  it("mở thường: lượt chưa nộp mới nhất; không có thì null (tạo lượt mới)", () => {
    expect(pickAttempt([done, one], { redo: false, wantResult: false })).toEqual(one);
    expect(pickAttempt([done], { redo: false, wantResult: false })).toBeNull();
    expect(pickAttempt([], { redo: false, wantResult: false })).toBeNull();
  });

  it("?view=result: lượt đã nộp mới nhất; không có thì lượt chưa nộp", () => {
    expect(pickAttempt([one, done], { redo: false, wantResult: true })).toEqual(done);
    expect(pickAttempt([one], { redo: false, wantResult: true })).toEqual(one);
  });

  it("?redo=1: luôn tạo lượt mới", () => {
    expect(pickAttempt([one, done], { redo: true, wantResult: false })).toBeNull();
  });
});
