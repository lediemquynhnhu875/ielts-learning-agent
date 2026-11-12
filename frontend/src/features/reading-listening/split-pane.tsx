"use client";

import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import { ResizeIcon } from "@/components/icons";
import { storageGet, storageSet } from "@/lib/storage";
import { clampRatio, DEFAULT_RATIO, GUTTER, splitBounds } from "./split";

const KEY = "rl-split";
const STEP = 0.05;

// `relative`: giữ phần tử absolute bên trong (chữ sr-only) trong vùng cuộn, không kéo dài cả trang.
// `scroll-cards` + đệm/margin âm 12px: bóng card không bị mép vùng cuộn cắt, mép card vẫn thẳng hàng (xem globals.css).
// Nền flex 30px bù đúng phần đệm đó và 6px thanh cuộn, nên bề rộng card chia đúng theo tỉ lệ.
const column =
  "scroll-thin scroll-cards relative flex min-w-0 flex-col min-[1150px]:min-h-0 min-[1150px]:overflow-y-auto min-[1150px]:-mx-3 min-[1150px]:-mt-2 min-[1150px]:-mb-4 min-[1150px]:px-3 min-[1150px]:pt-2 min-[1150px]:pb-4";

type SplitPaneProps = { left: ReactNode; right: ReactNode; leftClass?: string; rightClass?: string };

/**
 * Hai cột của màn làm bài và màn kết quả (bài đọc/script bên trái, câu hỏi bên phải), cuộn độc lập.
 * Từ 1150px có nút kéo tròn giữa khe (chuột, cảm ứng, phím ←/→, Home/End, nhấp đúp về mặc định); hẹp hơn thì xếp dọc.
 * Hai cột cao bằng vùng nhìn thấy và cuộn bên trong, nên nút căn giữa khe là luôn ở giữa màn hình.
 * Tỉ lệ lưu trong trình duyệt, dùng chung cho hai màn.
 */
export function SplitPane({ left, right, leftClass = "", rightClass = "" }: SplitPaneProps) {
  const box = useRef<HTMLDivElement>(null);
  // Tỉ lệ đang kéo; null là không kéo. Lưu bằng ref vì pointerup có thể tới trước khi lần kéo cuối kịp vẽ lại.
  const dragged = useRef<number | null>(null);
  const [ratio, setRatio] = useState(DEFAULT_RATIO);
  const [width, setWidth] = useState(0);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    // localStorage chỉ đọc sau khi gắn vào trình duyệt; storageGet đã bọc try/catch.
    let cancelled = false;
    void Promise.resolve().then(() => {
      const saved = storageGet(KEY);
      if (!cancelled && saved !== null) setRatio(clampRatio(Number(saved), 0));
    });
    return () => {
      cancelled = true;
      observer.disconnect();
    };
  }, []);

  const [low, high] = splitBounds(width);
  const shown = clampRatio(ratio, width);

  function commit(next: number) {
    const value = clampRatio(next, width);
    setRatio(value);
    storageSet(KEY, String(value));
  }

  function drag(e: PointerEvent<HTMLDivElement>) {
    if (dragged.current === null || !box.current) return;
    const rect = box.current.getBoundingClientRect();
    dragged.current = clampRatio((e.clientX - rect.left - GUTTER / 2) / (rect.width - GUTTER), rect.width);
    setRatio(dragged.current);
  }

  function release() {
    if (dragged.current === null) return;
    storageSet(KEY, String(dragged.current));
    dragged.current = null;
    setDragging(false);
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const next = { ArrowLeft: shown - STEP, ArrowRight: shown + STEP, Home: low, End: high }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    commit(next);
  }

  return (
    <div
      ref={box}
      style={{ "--split": shown } as CSSProperties}
      className="flex min-h-0 flex-1 flex-col gap-5 min-[1150px]:flex-row min-[1150px]:gap-3"
    >
      <div className={`${column} min-[1150px]:flex-[var(--split)_1_30px] ${leftClass}`}>{left}</div>
      <div
        role="separator"
        tabIndex={0}
        aria-orientation="vertical"
        aria-label="Thanh chia hai cột, phần trăm bề rộng cột trái"
        aria-valuenow={Math.round(shown * 100)}
        aria-valuemin={Math.round(low * 100)}
        aria-valuemax={Math.round(high * 100)}
        title="Kéo để đổi bề rộng, nhấp đúp để về mặc định"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          dragged.current = shown;
          setDragging(true);
        }}
        onPointerMove={drag}
        onPointerUp={release}
        onPointerCancel={release}
        onDoubleClick={() => commit(DEFAULT_RATIO)}
        onKeyDown={onKey}
        data-dragging={dragging || undefined}
        className="group relative hidden w-8 shrink-0 cursor-col-resize touch-none items-center justify-center outline-none min-[1150px]:flex"
      >
        {/* Đường kẻ chỉ hiện khi rê chuột, focus hoặc đang kéo, để lúc thường không lẫn với thanh cuộn. */}
        <span
          aria-hidden="true"
          className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-navy/30 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 group-data-[dragging]:opacity-100"
        />
        {/* before: nới vùng bấm của nút 32px lên 44px. */}
        <span className="glass-card relative grid size-8 place-items-center rounded-full text-navy before:absolute before:-inset-1.5 group-focus-visible:outline-2 group-focus-visible:outline-offset-2 group-focus-visible:outline-navy">
          <ResizeIcon size={16} />
        </span>
      </div>
      <div className={`${column} min-[1150px]:flex-[calc(1_-_var(--split))_1_30px] ${rightClass}`}>{right}</div>
    </div>
  );
}
