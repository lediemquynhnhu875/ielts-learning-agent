"use client";

import { useEffect, useState } from "react";
import { SparkleIcon } from "@/components/icons";
import { skillLabel } from "@/mock-data/types";
import type { CreateRequest } from "./create-job";

/** Một lần bấm "Tạo bài": đang chờ backend, hoặc đã lỗi (giữ lại để thử lại). */
export type CreateJob = { id: string; request: CreateRequest; startedAt: number } & (
  | { state: "running" }
  | { state: "failed"; message: string; traceId: string | null }
);

const SEGMENTS = 5;

/**
 * Card bài người học đang tạo. Backend trả kết quả một lần sau khi sinh và kiểm chứng xong
 * (không báo từng bước), nên thanh tiến trình chạy liên tục kèm thời gian đã chờ.
 */
export function GeneratingCard({ job, onRetry, onDismiss }: { job: CreateJob; onRetry: () => void; onDismiss: () => void }) {
  const failed = job.state === "failed";
  const { request } = job;

  return (
    <div
      aria-live="polite"
      className={`glass-card grid min-h-[118px] grid-cols-[64px_minmax(0,1fr)] items-center gap-x-4 gap-y-3 rounded-[26px] py-3.5 pl-3.5 pr-5 sm:grid-cols-[88px_minmax(0,1fr)_auto] sm:gap-5 sm:pr-6 ${
        failed
          ? "bg-[#fdeeee]/90 shadow-[0_0_0_2px_rgb(200_80_80/0.55),0_12px_30px_rgb(200_80_80/0.15)]"
          : "bg-[#fff4e2]/90 shadow-[0_0_0_2px_#eba45e,0_12px_30px_rgb(235_164_94/0.3)]"
      }`}
    >
      <span
        className={`grid size-16 place-items-center self-start rounded-[18px] text-navy sm:size-[88px] sm:self-center sm:rounded-[20px] ${
          failed
            ? "bg-status-rejected/12"
            : "bg-[repeating-linear-gradient(115deg,rgb(235_164_94/0.22)_0_14px,rgb(235_164_94/0.38)_14px_28px)]"
        }`}
      >
        <SparkleIcon size={34} strokeWidth={1.8} className="size-7 sm:size-9" />
      </span>

      <div className="min-w-0">
        <b className="block truncate text-base font-bold leading-[1.3] sm:text-[17px]" title={request.topic}>
          {request.topic}
        </b>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Chip>{skillLabel[request.skill]}</Chip>
          <Chip>Band {request.targetBand.toFixed(1)}</Chip>
          <Chip>{request.questionCount} câu</Chip>
        </div>
        {job.state === "failed" ? (
          <div className="mt-2.5 text-[13px] font-semibold text-status-rejected-text">
            {job.message}
            {job.traceId && (
              <span className="mt-1 block whitespace-nowrap text-xs font-medium text-muted" title={job.traceId}>
                Mã tra cứu: {job.traceId.slice(0, 8)}
              </span>
            )}
          </div>
        ) : (
          <div className="mt-2.5 flex flex-wrap items-center gap-2.5">
            <span className="flex gap-[5px]" role="progressbar" aria-label="Đang tạo bài">
              {Array.from({ length: SEGMENTS }, (_, i) => (
                <i
                  key={i}
                  className="block h-[7px] w-7 animate-pulse rounded bg-navy/70 motion-reduce:animate-none"
                  style={{ animationDelay: `${i * 160}ms` }}
                />
              ))}
            </span>
            <span className="text-[13px] font-semibold text-[#8a5a1e]">
              Đang tạo và kiểm chứng · <Elapsed since={job.startedAt} />
            </span>
          </div>
        )}
      </div>

      {failed ? (
        <div className="col-span-2 flex gap-2 justify-self-end sm:col-span-1">
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-full border border-navy/25 bg-white/70 px-4 py-2.5 text-sm font-semibold text-muted hover:text-navy-deep"
          >
            Bỏ qua
          </button>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-full bg-navy px-[18px] py-2.5 text-sm font-semibold text-cream"
          >
            Thử lại
          </button>
        </div>
      ) : (
        <span className="col-span-2 justify-self-end rounded-full border border-navy/25 bg-white/70 px-[18px] py-2.5 text-sm font-semibold text-muted sm:col-span-1">
          Chờ kiểm chứng
        </span>
      )}
    </div>
  );
}

/** Thời gian đã chờ, dạng m:ss, cập nhật mỗi giây. */
function Elapsed({ since }: { since: number }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - since) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [since]);
  return (
    <span className="tabular-nums">
      {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
    </span>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-navy/12 bg-white/75 px-2.5 py-[3px] text-xs font-semibold text-navy-deep">
      {children}
    </span>
  );
}
