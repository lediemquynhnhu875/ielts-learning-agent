import { describe, expect, it } from "vitest";
import { countStatuses, defaultFilter, filterQuestions, reasonText, segmentForEvidence, statusOf } from "./result-view";

describe("reasonText", () => {
  it("chỉ ba lý do cần giải thích mới có câu tiếng Việt", () => {
    expect(reasonText("word_limit_exceeded")).toBe("Câu trả lời vượt quá số từ cho phép");
    expect(reasonText("invalid_option")).toBe("Câu trả lời không phải một lựa chọn của câu này");
    expect(reasonText("invalid_classification")).toBe("Chỉ nhận TRUE, FALSE hoặc NOT GIVEN");
  });

  it("đúng, sai thường, bỏ trống và lý do lạ thì không có dòng lý do", () => {
    for (const reason of ["correct", "incorrect", "unanswered", "something_new"]) expect(reasonText(reason)).toBeNull();
  });
});

describe("statusOf, countStatuses, filterQuestions, defaultFilter", () => {
  const q = (reason: string) => ({ reason, is_correct: reason === "correct" });
  const list = [q("correct"), q("incorrect"), q("unanswered"), q("word_limit_exceeded"), q("unanswered"), q("invalid_option")];

  it("ba trạng thái: đúng, sai, bỏ trống (chưa trả lời không tính là sai)", () => {
    expect(list.map(statusOf)).toEqual(["correct", "wrong", "blank", "wrong", "blank", "wrong"]);
  });

  it("đếm theo trạng thái", () => {
    expect(countStatuses(list)).toEqual({ all: 6, wrong: 3, blank: 2, correct: 1 });
    expect(countStatuses([])).toEqual({ all: 0, wrong: 0, blank: 0, correct: 0 });
  });

  it("lọc giữ thứ tự; Tất cả trả đủ", () => {
    expect(filterQuestions(list, "all")).toEqual(list);
    expect(filterQuestions(list, "blank")).toEqual([list[2], list[4]]);
    expect(filterQuestions(list, "correct")).toEqual([list[0]]);
    expect(filterQuestions(list, "wrong")).toHaveLength(3);
  });

  it("mặc định mở Sai nếu có câu sai, không thì Tất cả", () => {
    expect(defaultFilter(countStatuses(list))).toBe("wrong");
    expect(defaultFilter(countStatuses([q("correct"), q("unanswered")]))).toBe("all");
  });
});

describe("segmentForEvidence", () => {
  // Script: mốc ký tự của backend tính theo code point (Python), không phải UTF-16.
  const text = "Host: Hi 😀 there.\nGuest: I would like a room for two nights.\nHost: Of course.";
  const cp = (needle: string) => Array.from(text.slice(0, text.indexOf(needle))).length;
  const turn = (speech: string, start_seconds: number, end_seconds: number) => ({
    start_seconds,
    end_seconds,
    source_start_char: cp(speech),
    source_end_char: cp(speech) + Array.from(speech).length,
  });
  const turns = [turn("Hi 😀 there.", 0, 2), turn("I would like a room for two nights.", 2, 5.5), turn("Of course.", 5.5, 7)];

  it("trả đoạn của lượt chứa bằng chứng, đúng cả khi phía trước có ký tự ngoài BMP", () => {
    expect(segmentForEvidence(turns, text, "a room for two nights")).toEqual({ start_seconds: 2, end_seconds: 5.5 });
    expect(segmentForEvidence(turns, text, "Of course")).toEqual({ start_seconds: 5.5, end_seconds: 7 });
    expect(segmentForEvidence(turns, text, "Hi 😀")).toEqual({ start_seconds: 0, end_seconds: 2 });
  });

  it("bằng chứng vắt qua nhiều lượt: từ đầu lượt đầu tới cuối lượt cuối", () => {
    expect(segmentForEvidence(turns, text, "two nights.\nHost: Of course")).toEqual({ start_seconds: 2, end_seconds: 7 });
  });

  it("không có bằng chứng, không có trong script hoặc không có lượt thì null", () => {
    expect(segmentForEvidence(turns, text, null)).toBeNull();
    expect(segmentForEvidence(turns, text, "  ")).toBeNull();
    expect(segmentForEvidence(turns, text, "three nights")).toBeNull();
    expect(segmentForEvidence([], text, "Of course")).toBeNull();
  });

  it("bỏ lượt có mốc thời gian không phát được", () => {
    expect(segmentForEvidence([{ ...turns[2], end_seconds: 5.5 }], text, "Of course")).toBeNull();
  });
});
