import { describe, expect, it } from "vitest";
import { draftKey, parseDraft } from "./draft";

const now = Date.UTC(2026, 9, 31, 7, 0, 0);

describe("parseDraft", () => {
  it("chưa có nháp thì bắt đầu mới: giờ bắt đầu là bây giờ, bài trống, có mã lượt làm", () => {
    const draft = parseDraft(null, now);
    expect(draft).toMatchObject({ text: "", startedAt: now, savedAt: null });
    expect(draft.attemptId).toMatch(/^att_/);
  });

  it("đọc lại nháp đã lưu, giữ giờ bắt đầu để đồng hồ không chạy lại", () => {
    const saved = JSON.stringify({ text: "Hello", startedAt: now - 60_000, savedAt: now - 5_000, attemptId: "att_x" });
    expect(parseDraft(saved, now)).toEqual({ text: "Hello", startedAt: now - 60_000, savedAt: now - 5_000, attemptId: "att_x" });
  });

  it("nháp hỏng hoặc sai kiểu thì bắt đầu mới, không làm vỡ trang", () => {
    expect(parseDraft("{không phải json", now).text).toBe("");
    expect(parseDraft(JSON.stringify({ text: 5, startedAt: "x" }), now)).toMatchObject({ text: "", startedAt: now });
  });
});

describe("draftKey", () => {
  it("mỗi đề một khoá riêng", () => {
    expect(draftKey("wr-001")).toBe("writing-draft:wr-001");
  });
});
