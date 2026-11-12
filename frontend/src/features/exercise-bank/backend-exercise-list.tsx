"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { listExercises } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { Rise } from "./admin-exercise-bank";
import { ExerciseCard } from "./exercise-card";
import { hasMore, initialList, listReducer, PAGE_SIZE, type ListState } from "./exercise-list";

const messageOf = (error: unknown) => (error instanceof ApiError ? error.message : "Lỗi không xác định.");

export type ExerciseListQuery = {
  /** Không có: cả Reading và Listening. */
  skill?: "reading" | "listening";
  /** Ô tìm bài; backend tìm trong tiêu đề và chủ đề. */
  query: string;
  /** `false`: tab không có bài Reading/Listening (Writing, Speaking), không gọi backend. */
  enabled: boolean;
};

/**
 * Danh sách bài Reading/Listening đã kiểm chứng từ GET /api/exercises, lấy theo trang ("Xem thêm").
 * Đổi kỹ năng hoặc ô tìm (chờ 300ms ngưng gõ) thì lấy lại từ trang đầu; `reload` lấy lại sau khi tạo bài.
 */
export function useExerciseList({ skill, query, enabled }: ExerciseListQuery) {
  const [state, dispatch] = useReducer(listReducer, initialList);
  const [q, setQ] = useState(query.trim());
  const [round, setRound] = useState(0);
  // Số thứ tự của bộ lọc hiện tại: phản hồi của bộ lọc cũ tới muộn thì bỏ.
  const generation = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => setQ(query.trim()), 300);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!enabled) return;
    const current = ++generation.current;
    dispatch({ type: "load" });
    listExercises({ skill, q, limit: PAGE_SIZE, offset: 0 }).then(
      (page) => current === generation.current && dispatch({ type: "page", items: page.items, total: page.total, offset: 0 }),
      (error) => current === generation.current && dispatch({ type: "failed", message: messageOf(error) }),
    );
  }, [skill, q, enabled, round]);

  const loadMore = useCallback(() => {
    if (state.loadingMore || !hasMore(state)) return;
    const current = generation.current;
    const offset = state.loaded;
    dispatch({ type: "more" });
    listExercises({ skill, q, limit: PAGE_SIZE, offset }).then(
      (page) => current === generation.current && dispatch({ type: "page", items: page.items, total: page.total, offset }),
      (error) => current === generation.current && dispatch({ type: "failed", message: messageOf(error) }),
    );
  }, [state, skill, q]);

  const reload = useCallback(() => setRound((n) => n + 1), []);
  return { state, loadMore, reload };
}

const pill =
  "inline-flex min-h-11 items-center justify-center rounded-full px-6 text-[15px] font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy disabled:cursor-not-allowed disabled:opacity-50";

type BackendExerciseListProps = {
  state: ListState;
  onLoadMore: () => void;
  onRetry: () => void;
  /** `mock`: thẻ ở trang Thi thử. */
  variant: "learner" | "mock";
};

/** Phần danh sách lấy từ backend: đang tải, lỗi (kèm Thử lại), các thẻ, và "Xem thêm" theo tổng số bài. Danh sách rỗng do nơi gọi báo. */
export function BackendExerciseList({ state, onLoadMore, onRetry, variant }: BackendExerciseListProps) {
  if (state.status === "loading") {
    return (
      <div aria-busy="true" aria-label="Đang tải danh sách bài" className="flex flex-col gap-3.5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="glass-card h-[118px] animate-pulse rounded-[26px] motion-reduce:animate-none" />
        ))}
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div role="alert" className="glass flex flex-col items-start gap-3 rounded-[26px] px-6 py-6">
        <b className="text-lg">Chưa tải được danh sách bài Reading và Listening</b>
        <p className="text-[15px] text-muted">{state.message}</p>
        <button type="button" onClick={onRetry} className={`${pill} bg-navy text-cream`}>
          Thử lại
        </button>
      </div>
    );
  }

  return (
    <>
      {state.cards.map((card, i) => (
        <Rise key={card.id} index={i % PAGE_SIZE}>
          <ExerciseCard card={card} variant={variant} />
        </Rise>
      ))}
      {state.total > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 py-1">
          <p aria-live="polite" className="text-sm text-muted">
            {state.message ?? `Đang hiện ${state.cards.length}/${state.total} bài Reading và Listening`}
          </p>
          {hasMore(state) && (
            <button type="button" onClick={onLoadMore} disabled={state.loadingMore} className={`${pill} border border-navy/25 bg-white/70 hover:bg-white`}>
              {state.loadingMore ? "Đang tải…" : state.message ? "Thử lại" : "Xem thêm"}
            </button>
          )}
        </div>
      )}
    </>
  );
}
