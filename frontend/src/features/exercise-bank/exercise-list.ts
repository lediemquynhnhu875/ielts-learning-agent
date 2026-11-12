import type { ExerciseSummary } from "@/lib/api/types";
import type { ExerciseCard } from "@/mock-data/exercises";
import { questionKindLabel } from "@/mock-data/reading-listening";

/** Số bài mỗi trang, bằng mặc định của GET /api/exercises. */
export const PAGE_SIZE = 20;

/** Thẻ Kho đề từ bản tóm tắt của GET /api/exercises: chip số câu, dòng phụ là các dạng câu. */
export function summaryToCard(summary: ExerciseSummary): ExerciseCard {
  const labels: Record<string, string> = questionKindLabel;
  return {
    id: summary.id,
    skill: summary.skill,
    title: summary.title,
    status: summary.status,
    targetBand: summary.target_band,
    sizeLabel: `${summary.question_count} câu`,
    detailLine: summary.question_types.map((kind) => labels[kind] ?? kind).join(" · "),
    reportCount: 0,
    createdAt: summary.created_at,
  };
}

/** Danh sách bài Reading/Listening lấy theo trang từ backend. */
export type ListState = {
  /** Trạng thái của trang đầu; đang lấy trang sau là `loadingMore`. */
  status: "loading" | "ready" | "error";
  cards: ExerciseCard[];
  /** Tổng số bài khớp bộ lọc (trước phân trang). */
  total: number;
  /** Số bài backend đã trả, dùng làm offset của trang sau (khác số thẻ khi có bài trùng bị bỏ). */
  loaded: number;
  loadingMore: boolean;
  /** Thông điệp lỗi: của trang đầu khi `status = error`, của lần "Xem thêm" khi `status = ready`. */
  message: string | null;
};

export type ListEvent =
  | { type: "load" }
  | { type: "more" }
  | { type: "page"; items: ExerciseSummary[]; total: number; offset: number }
  | { type: "failed"; message: string };

export const initialList: ListState = { status: "loading", cards: [], total: 0, loaded: 0, loadingMore: false, message: null };

export function listReducer(state: ListState, event: ListEvent): ListState {
  switch (event.type) {
    case "load":
      return initialList;
    case "more":
      return { ...state, loadingMore: true, message: null };
    case "page": {
      const previous = event.offset === 0 ? [] : state.cards;
      // Bài mới tạo chen vào đầu danh sách làm trang sau lặp lại bài cuối trang trước: bỏ bài trùng.
      const seen = new Set(previous.map((card) => card.id));
      const added = event.items.map(summaryToCard).filter((card) => !seen.has(card.id));
      return { status: "ready", cards: [...previous, ...added], total: event.total, loaded: event.offset + event.items.length, loadingMore: false, message: null };
    }
    case "failed":
      // Lỗi khi "Xem thêm" giữ các bài đã có; lỗi trang đầu thì cả danh sách ở trạng thái lỗi.
      return state.loadingMore ? { ...state, loadingMore: false, message: event.message } : { ...initialList, status: "error", message: event.message };
  }
}

export const hasMore = (state: ListState) => state.status === "ready" && state.loaded < state.total;
