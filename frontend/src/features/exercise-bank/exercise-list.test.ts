import { describe, expect, it } from "vitest";
import type { ExerciseSummary } from "@/lib/api/types";
import { hasMore, initialList, listReducer, PAGE_SIZE, summaryToCard, type ListState } from "./exercise-list";

const summary = (id: string, extra: Partial<ExerciseSummary> = {}): ExerciseSummary => ({
  id,
  title: `Bài ${id}`,
  skill: "reading",
  topic: "Mangroves",
  target_band: 6,
  source: "llm_generated_verified",
  status: "verified",
  created_at: "2026-11-11T03:00:00Z",
  question_count: 10,
  question_types: ["multiple_choice", "sentence_completion", "true_false_not_given"],
  ...extra,
});

describe("summaryToCard", () => {
  it("thẻ Kho đề từ bản tóm tắt: số câu và các dạng câu", () => {
    expect(summaryToCard(summary("a", { skill: "listening", target_band: 5.5, question_count: 8 }))).toEqual({
      id: "a",
      skill: "listening",
      title: "Bài a",
      status: "verified",
      targetBand: 5.5,
      sizeLabel: "8 câu",
      detailLine: "MCQ · Fill · T/F/NG",
      reportCount: 0,
      createdAt: "2026-11-11T03:00:00Z",
    });
  });

  it("dạng câu lạ hiện nguyên tên; không có dạng nào thì dòng phụ rỗng", () => {
    expect(summaryToCard(summary("a", { question_types: ["matching_headings", "new_kind"] as ExerciseSummary["question_types"] })).detailLine).toBe("Heading · new_kind");
    expect(summaryToCard(summary("a", { question_types: [] })).detailLine).toBe("");
  });
});

describe("listReducer", () => {
  const page = (ids: string[], total: number, offset: number) => ({ type: "page" as const, items: ids.map((id) => summary(id)), total, offset });
  const ids = (state: ListState) => state.cards.map((c) => c.id);

  it("mở đầu là đang tải; trang đầu về thì sẵn sàng, có tổng số", () => {
    expect(initialList.status).toBe("loading");
    const state = listReducer(initialList, page(["a", "b"], 5, 0));
    expect(state).toMatchObject({ status: "ready", total: 5, loaded: 2, loadingMore: false, message: null });
    expect(ids(state)).toEqual(["a", "b"]);
    expect(hasMore(state)).toBe(true);
  });

  it("Xem thêm: nối trang sau, bỏ bài trùng (có bài mới chen vào làm lệch offset), hết thì không còn Xem thêm", () => {
    let state = listReducer(initialList, page(["a", "b"], 4, 0));
    state = listReducer(state, { type: "more" });
    expect(state.loadingMore).toBe(true);
    state = listReducer(state, page(["b", "c"], 4, 2));
    expect(ids(state)).toEqual(["a", "b", "c"]);
    expect(state).toMatchObject({ loaded: 4, loadingMore: false });
    expect(hasMore(state)).toBe(false);
  });

  it("đổi bộ lọc: về đang tải và bỏ danh sách cũ", () => {
    const state = listReducer(listReducer(initialList, page(["a"], 1, 0)), { type: "load" });
    expect(state).toEqual(initialList);
  });

  it("danh sách rỗng: sẵn sàng, không có thẻ, không có Xem thêm", () => {
    const state = listReducer(initialList, page([], 0, 0));
    expect(state).toMatchObject({ status: "ready", total: 0 });
    expect(ids(state)).toEqual([]);
    expect(hasMore(state)).toBe(false);
  });

  it("lỗi trang đầu: trạng thái lỗi kèm thông điệp; lỗi khi Xem thêm: giữ danh sách, báo lỗi ở nút", () => {
    expect(listReducer(initialList, { type: "failed", message: "Không kết nối được backend." })).toMatchObject({ status: "error", message: "Không kết nối được backend.", cards: [] });
    let state = listReducer(initialList, page(["a", "b"], 5, 0));
    state = listReducer(listReducer(state, { type: "more" }), { type: "failed", message: "Lỗi" });
    expect(state).toMatchObject({ status: "ready", loadingMore: false, message: "Lỗi" });
    expect(ids(state)).toEqual(["a", "b"]);
    expect(hasMore(state)).toBe(true);
  });

  it("mỗi trang 20 bài, bằng mặc định của backend", () => {
    expect(PAGE_SIZE).toBe(20);
  });
});
