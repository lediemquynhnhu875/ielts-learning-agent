"use client";

import { useMemo, useRef, useState } from "react";
import { AttemptPicker } from "@/components/attempt-picker";
import { XIcon } from "@/components/icons";
import type { WritingAssessment } from "@/lib/api/writing";
import type { WritingTask } from "@/mock-data/writing";
import { segmentEssay } from "./evidence";
import { forDownload, formatBand, toResultView, type CriterionView } from "./result-view";
import type { SavedResult } from "./saved-result";
import { formatDuration } from "./text";
import { ScoreMedal, WritingHeader } from "./writing-header";

const DISCLAIMER = "Điểm ước lượng do AI chấm, chỉ dùng để luyện tập, không thay thế điểm thi chính thức.";

/** Màu tô dẫn chứng theo tiêu chí; luôn đi kèm mã tiêu chí bằng chữ (chú thích và nút tiêu chí). */
const highlight: Record<string, string> = {
  TR: "bg-orange/35 shadow-[inset_0_-2px_0_#a8571a]",
  TA: "bg-orange/35 shadow-[inset_0_-2px_0_#a8571a]",
  CC: "bg-skill-writing/20 shadow-[inset_0_-2px_0_#4f7bc4]",
  LR: "bg-sky/35 shadow-[inset_0_-2px_0_#213d68]",
  GRA: "bg-skill-speaking/18 shadow-[inset_0_-2px_0_#8e2f1f]",
};

function downloadJson(result: WritingAssessment) {
  const blob = new Blob([JSON.stringify(forDownload(result), null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `writing-${result.attempt_id}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

const buttonBase =
  "inline-flex min-h-11 items-center justify-center rounded-full px-5 text-[15px] font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy";

type WritingResultProps = {
  title: string;
  task: WritingTask;
  /** Các lượt đã chấm, mới nhất trước; mở lượt đầu tiên. */
  attempts: SavedResult[];
};

/** Màn kết quả: ô điểm, 4 tiêu chí kèm điểm giám khảo A, B, bài có dẫn chứng tô sáng, sửa lỗi; chọn xem lại các lượt trước. */
export function WritingResult({ title, task, attempts }: WritingResultProps) {
  const [index, setIndex] = useState(0);
  const { result, essay, sample, durationSec } = attempts[Math.min(index, attempts.length - 1)];
  const view = useMemo(() => toResultView(result, task), [result, task]);
  const [selected, setSelected] = useState<string | null>(null);
  const essayRef = useRef<HTMLDivElement>(null);

  const spans = selected ? view.spans.filter((s) => s.criterion === selected) : view.spans;
  const segments = useMemo(() => segmentEssay(essay, spans), [essay, spans]);
  const present = view.criteria.filter((c) => view.spans.some((s) => s.criterion === c.code)).map((c) => c.code);
  const selectedComment = view.criteria.find((c) => c.code === selected)?.comment;
  const meta = ["Kết quả", `${result.word_count} từ`];
  if (durationSec !== undefined) meta.push(formatDuration(durationSec));

  function select(code: string) {
    const next = selected === code ? null : code;
    setSelected(next);
    if (!next) return;
    // Đợi vẽ lại rồi cuộn tới dẫn chứng đầu tiên của tiêu chí.
    requestAnimationFrame(() => {
      const mark = essayRef.current?.querySelector<HTMLElement>(`mark[data-criterion~="${next}"]`);
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      mark?.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    });
  }

  const notices: string[] = [];
  if (sample) notices.push("Chế độ mô phỏng: Task 1 chưa chấm thật, điểm và nhận xét là dữ liệu mẫu.");
  if (view.kind === "demo") notices.push("Chế độ mô phỏng: không có điểm.");
  if (view.kind === "provisional") notices.push("Hai giám khảo lệch nhiều; điểm đang tạm tính, cần giáo viên xem.");

  return (
    <div className="flex flex-col gap-4 lg:h-[calc(100dvh-3.5rem)]">
      <WritingHeader
        title={title}
        meta={meta}
        aside={<ScoreMedal value={formatBand(view.overall)} note={view.kind === "provisional" ? "Tạm tính" : undefined} />}
      />
      {(attempts.length > 1 || notices.length > 0) && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {attempts.length > 1 && (
            <AttemptPicker
              attempts={attempts.map((a) => ({ id: a.result.attempt_id, value: formatBand(toResultView(a.result, task).overall), savedAt: a.savedAt }))}
              activeId={attempts[Math.min(index, attempts.length - 1)].result.attempt_id}
              valueLabel="điểm"
              onSelect={(id) => {
                setIndex(attempts.findIndex((a) => a.result.attempt_id === id));
                setSelected(null);
              }}
            />
          )}
          {notices.map((n) => (
            <p key={n} className="glass rounded-full bg-white/55 px-5 py-2 text-sm">
              {n}
            </p>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-2 gap-3 md:gap-4 min-[1200px]:grid-cols-4">
          {view.criteria.map((c) => (
            <CriterionTile key={c.code} criterion={c} pressed={selected === c.code} onClick={() => select(c.code)} />
          ))}
        </div>
        {selected && selectedComment && (
          <section
            aria-label={`Nhận xét ${selected}`}
            aria-live="polite"
            className="glass flex items-start gap-4 rounded-[24px] bg-white/55 py-3.5 pr-3 pl-5"
          >
            <span className={`mt-0.5 shrink-0 rounded-lg px-2 py-0.5 text-[13px] font-bold ${highlight[selected] ?? highlight.TR}`}>{selected}</span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-semibold text-muted">Nhận xét của giám khảo</p>
              <p className="mt-0.5 text-[15px] leading-relaxed">{selectedComment}</p>
            </div>
            <button
              type="button"
              aria-label="Đóng nhận xét"
              onClick={() => setSelected(null)}
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-full text-muted hover:bg-white/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
            >
              <XIcon width={18} height={18} />
            </button>
          </section>
        )}
        <p className="text-center text-xs text-muted">{DISCLAIMER}</p>
      </div>

      <div className="flex flex-col gap-4 lg:min-h-0 lg:flex-1 lg:flex-row">
        <section aria-labelledby="essay-title" className="glass-paper flex min-w-0 flex-col gap-3 rounded-[28px] p-6 lg:min-h-0 lg:flex-[3]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="essay-title" className="text-[19px] font-bold">
              {sample ? "Bài mẫu" : "Bài của bạn"} <span className="text-[13px] font-medium text-muted">{result.word_count} từ</span>
            </h2>
            {present.length > 0 && (
              <ul aria-label="Chú thích dẫn chứng" className="flex gap-2 text-[13px]">
                {present.map((code) => (
                  <li key={code} className={`rounded-md px-1 ${highlight[code]}`}>
                    {code}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {view.flags.map((f) => (
            <p key={f} className="text-[13px] text-status-spare-text">
              {f}
            </p>
          ))}
          <div ref={essayRef} className="scroll-thin whitespace-pre-wrap text-base leading-[1.8] lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
            {segments.map((seg) =>
              seg.criteria.length === 0 ? (
                <span key={seg.start}>{seg.text}</span>
              ) : (
                <mark
                  key={seg.start}
                  data-criterion={seg.criteria.join(" ")}
                  title={`Dẫn chứng ${seg.criteria.join(", ")}`}
                  className={`rounded-md px-[3px] text-inherit ${highlight[seg.criteria[0]] ?? highlight.TR}`}
                >
                  {seg.text}
                </mark>
              ),
            )}
          </div>
        </section>

        <section aria-labelledby="fix-title" className="glass flex min-w-0 flex-col gap-3.5 rounded-[28px] p-6 lg:min-h-0 lg:flex-[2]">
          <h2 id="fix-title" className="text-[19px] font-bold">
            Sửa lỗi
          </h2>
          <div className="scroll-thin flex flex-col gap-2.5 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
            {view.corrections.length === 0 && (
              <p className="text-sm text-muted">{view.correctionsNote ?? "Chưa có gợi ý sửa."}</p>
            )}
            {view.corrections.map((c) => (
              <div key={`${c.original}-${c.suggestion}`} className="rounded-[20px] border border-white/75 bg-white/45 px-4 py-3">
                <span className="inline-flex rounded-full border border-navy/12 bg-white/75 px-3 py-[3px] text-[13px] font-semibold">
                  {c.category}
                </span>
                <p className="mt-1.5 text-[13px] text-muted line-through">{c.original}</p>
                <p className="font-bold">{c.suggestion}</p>
                <p className="text-[13px] text-muted">{c.reason}</p>
              </div>
            ))}
          </div>
          <div className="flex justify-center">
            <button type="button" onClick={() => downloadJson(result)} className={`${buttonBase} border border-navy/25 bg-white/70`}>
              Tải JSON
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}

function CriterionTile({ criterion: c, pressed, onClick }: { criterion: CriterionView; pressed: boolean; onClick: () => void }) {
  const judges = c.a !== null && c.b !== null ? `A ${formatBand(c.a)}, B ${formatBand(c.b)}` : null;
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`glass flex flex-col gap-2 rounded-[26px] px-5 py-4 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy ${
        pressed ? "bg-white/80 ring-2 ring-navy/40" : "hover:bg-white/60"
      }`}
    >
      <span className="flex items-center justify-between gap-2">
        <b>{c.code}</b>
        {c.disputed && (
          <span className="whitespace-nowrap rounded-full bg-orange/34 px-3 py-[3px] text-[13px] font-semibold text-status-spare-text">Đã qua đối chiếu</span>
        )}
      </span>
      <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className={`text-[40px] font-extrabold leading-none tracking-[-0.02em] ${c.band === null ? "text-muted/45" : ""}`}>
          {formatBand(c.band)}
        </span>
        {judges && <span className="text-[13px] text-muted">{judges}</span>}
      </span>
    </button>
  );
}

type WritingFailedProps = {
  title: string;
  task: WritingTask;
  wordCount: number;
  /** Thông điệp của backend, hiển thị nguyên văn. */
  message: string;
  /** Phản hồi `status: failed` của backend (để tải JSON); `null` khi lỗi trước khi có phản hồi. */
  result: WritingAssessment | null;
  onRetry: () => void;
};

/** Chấm lỗi: không có điểm, thông điệp nguyên văn, bài vẫn được giữ, nút Chấm lại. */
export function WritingFailed({ title, task, wordCount, message, result, onRetry }: WritingFailedProps) {
  const codes = [task === "task1" ? "TA" : "TR", "CC", "LR", "GRA"];
  return (
    <div className="flex flex-col gap-4 lg:h-[calc(100dvh-3.5rem)]">
      <WritingHeader title={title} meta={["Kết quả", `${wordCount} từ`]} aside={<ScoreMedal value="—" />} />
      <div className="grid grid-cols-2 gap-3 md:gap-4 min-[1200px]:grid-cols-4" aria-hidden="true">
        {codes.map((code) => (
          <div key={code} className="glass flex flex-col gap-2 rounded-[26px] px-5 py-4">
            <b>{code}</b>
            <span className="text-[40px] font-extrabold leading-none text-muted/45">—</span>
          </div>
        ))}
      </div>
      <section role="alert" className="glass flex flex-1 flex-col items-center justify-center gap-4 rounded-[28px] px-6 py-10 text-center">
        <b className="text-[22px]">Chưa chấm được</b>
        <p className="max-w-[60ch] text-[#5c1d12]">{message}</p>
        <p className="text-[13px] text-muted">Bài của bạn vẫn được giữ.</p>
        <div className="flex flex-wrap justify-center gap-3">
          <button type="button" onClick={onRetry} className={`${buttonBase} min-h-12 bg-navy px-7 text-cream`}>
            Chấm lại
          </button>
          {result && (
            <button type="button" onClick={() => downloadJson(result)} className={`${buttonBase} min-h-12 border border-navy/25 bg-white/70`}>
              Tải JSON
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
