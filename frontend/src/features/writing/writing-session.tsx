"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ClockIcon, ExpandIcon, XIcon } from "@/components/icons";
import { ApiError } from "@/lib/api/errors";
import { formatTime } from "@/lib/format";
import { storageGet, storageSet } from "@/lib/storage";
import { assessWriting, getWritingStatus, type WritingAssessment } from "@/lib/api/writing";
import { sampleTask1Result, writingTaskInfo, writingTitle, type WritingExercise } from "@/mock-data/writing";
import { BarChart, ChartLegend, ChartTable } from "./bar-chart";
import { draftKey, parseDraft, type WritingDraft } from "./draft";
import { readAttempts, saveAttempt, type SavedResult } from "./saved-result";
import { countWords, formatClock, remainingSeconds, wordRatio } from "./text";
import { WritingHeader, WritingClock } from "./writing-header";
import { WritingFailed, WritingResult } from "./writing-result";

export type WritingMode = "live" | "demo";

type Grader = { state: "checking" } | { state: "ready" } | { state: "blocked"; message: string };

type Phase =
  | { name: "writing" }
  | { name: "grading" }
  | { name: "result"; attempts: SavedResult[] }
  | { name: "failed"; message: string; result: WritingAssessment | null };

/** Trình duyệt chặn lưu trữ thì danh sách đọc lại có thể thiếu lượt vừa chấm: luôn hiện lượt đó. */
function keepCurrent(list: SavedResult[], current: SavedResult): SavedResult[] {
  return list[0]?.result.attempt_id === current.result.attempt_id ? list : [current, ...list];
}

async function fetchGrader(): Promise<Grader> {
  try {
    const status = await getWritingStatus();
    return status.rubric_ready ? { state: "ready" } : { state: "blocked", message: "Hiện chưa chấm được bài Writing." };
  } catch (error) {
    return { state: "blocked", message: error instanceof ApiError ? error.message : "Không kiểm tra được bộ chấm." };
  }
}

/**
 * Màn viết Writing: viết, đang chấm, kết quả, chấm lỗi.
 * Task 2 chấm qua backend Writing (route trung gian). Task 1 chưa có chấm ở backend:
 * nộp bài hiện kết quả mẫu trong `mock-data/writing.ts`, có ghi rõ không phải điểm bài của người học.
 */
export function WritingSession({ exercise, mode }: { exercise: WritingExercise; mode: WritingMode }) {
  const info = writingTaskInfo[exercise.task];
  const title = writingTitle(exercise);
  const usesBackend = exercise.task === "task2";

  const [draft, setDraft] = useState<WritingDraft | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [phase, setPhase] = useState<Phase>({ name: "writing" });
  const [grader, setGrader] = useState<Grader>({ state: usesBackend && mode === "live" ? "checking" : "ready" });
  const [announcement, setAnnouncement] = useState("");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const params = useSearchParams();
  const view = params.get("view");
  const redo = params.get("redo");

  // Nháp chỉ đọc sau khi gắn vào trình duyệt (server không có localStorage), nên trang server và trình duyệt khớp nhau.
  // `?redo=1` (nút "Làm lại" ở Kho đề): bỏ nháp, bắt đầu lượt mới; các lượt đã chấm vẫn giữ.
  // `?view=result` (nút "Xem kết quả"): mở thẳng lượt chấm gần nhất.
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      if (redo) storageSet(draftKey(exercise.id), "");
      const loaded = parseDraft(redo ? null : storageGet(draftKey(exercise.id)), Date.now());
      storageSet(draftKey(exercise.id), JSON.stringify(loaded));
      setDraft(loaded);
      // Next giữ trạng thái của trang đã ghé (Activity) khi chuyển trang trong app,
      // nên phải đặt lại màn theo nút vừa bấm: "Làm lại" về màn viết, "Xem kết quả" mở lượt mới nhất.
      const attempts = view === "result" ? readAttempts(exercise.id) : [];
      if (attempts.length > 0) setPhase({ name: "result", attempts });
      else if (redo) setPhase({ name: "writing" });
      // replaceState không tải lại trang server (router.replace thì có, đọc đề thêm một lần).
      if (redo || view) window.history.replaceState(null, "", `/writing/${exercise.id}`);
    });
    return () => {
      cancelled = true;
    };
  }, [exercise.id, redo, view]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Task 2 chấm thật cần rubric ở backend: kiểm tra trước khi cho nộp. Demo và Task 1 không cần.
  const needsCheck = usesBackend && mode === "live";
  useEffect(() => {
    if (!needsCheck) return;
    let cancelled = false;
    void fetchGrader().then((next) => {
      if (!cancelled) setGrader(next);
    });
    return () => {
      cancelled = true;
    };
  }, [needsCheck]);

  async function recheckGrader() {
    setGrader({ state: "checking" });
    setGrader(await fetchGrader());
  }

  const remaining = draft ? remainingSeconds(draft.startedAt, now, info.minutes) : info.minutes * 60;
  const timeUp = draft !== null && remaining === 0;

  function updateText(text: string) {
    if (!draft) return;
    const next = { ...draft, text };
    setDraft(next);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      const saved = { ...next, savedAt: Date.now() };
      storageSet(draftKey(exercise.id), JSON.stringify(saved));
      setDraft((current) => (current ? { ...current, savedAt: saved.savedAt } : current));
    }, 700);
  }

  async function submit() {
    if (!draft) return;
    const durationSec = Math.max(0, Math.round((Date.now() - draft.startedAt) / 1000));
    if (!usesBackend) {
      // Kết quả mẫu mang mã lượt của bài này để mỗi lần nộp là một lượt riêng.
      const result = { ...sampleTask1Result.result, attempt_id: draft.attemptId };
      const saved: SavedResult = { result, essay: sampleTask1Result.essay, sample: true, savedAt: Date.now(), durationSec };
      setPhase({ name: "result", attempts: keepCurrent(saveAttempt(exercise.id, saved), saved) });
      setAnnouncement("Đã hiện kết quả mẫu.");
      return;
    }
    setPhase({ name: "grading" });
    setAnnouncement("Đang chấm bài.");
    try {
      const result = await assessWriting({ promptText: exercise.prompt, essayText: draft.text, attemptId: draft.attemptId });
      if (result.status === "failed") {
        setPhase({ name: "failed", message: result.failure ?? "Chưa chấm được.", result });
        setAnnouncement("Chưa chấm được.");
      } else {
        const saved: SavedResult = { result, essay: draft.text, sample: false, savedAt: Date.now(), durationSec };
        setPhase({ name: "result", attempts: keepCurrent(saveAttempt(exercise.id, saved), saved) });
        setAnnouncement("Đã chấm xong.");
      }
    } catch (error) {
      setPhase({ name: "failed", message: error instanceof ApiError ? error.message : "Chưa chấm được.", result: null });
      setAnnouncement("Chưa chấm được.");
    }
  }

  const live = (
    <p aria-live="polite" className="sr-only">
      {timeUp && phase.name === "writing" ? "Hết giờ làm bài." : announcement}
    </p>
  );

  if (phase.name === "result") {
    return (
      <>
        {live}
        <WritingResult title={title} task={exercise.task} attempts={phase.attempts} />
      </>
    );
  }
  if (phase.name === "failed") {
    return (
      <>
        {live}
        <WritingFailed
          title={title}
          task={exercise.task}
          wordCount={draft ? countWords(draft.text) : 0}
          message={phase.message}
          result={phase.result}
          onRetry={submit}
        />
      </>
    );
  }

  const grading = phase.name === "grading";
  const text = draft?.text ?? "";
  const words = countWords(text);
  const ratio = wordRatio(words, info.minWords);
  const savedLine = draft?.savedAt ? `Đã lưu nháp lúc ${formatTime(draft.savedAt)}` : "Nháp tự lưu trên máy này";
  const blockedLine =
    grader.state === "checking" ? "Đang kiểm tra bộ chấm…" : grader.state === "blocked" ? grader.message : null;
  const canSubmit = draft !== null && !grading && grader.state === "ready" && words > 0;

  const header = (
    <WritingHeader
      title={title}
      meta={[exercise.essayType ?? info.label, `${info.minutes} phút`, `Tối thiểu ${info.minWords} từ`]}
      aside={<WritingClock label={formatClock(remaining)} ended={timeUp} />}
    />
  );

  const editor = (
    <div className="glass-paper relative flex min-h-[50vh] flex-1 flex-col overflow-hidden rounded-[28px] lg:min-h-0">
      {grading && <GradingOverlay />}
      <label htmlFor="essay" className="sr-only">
        Bài viết
      </label>
      <textarea
        id="essay"
        value={text}
        onChange={(e) => updateText(e.target.value)}
        readOnly={grading || draft === null || timeUp}
        spellCheck={false}
        autoCorrect="off"
        autoCapitalize="off"
        placeholder={draft === null ? "" : "Viết bài ở đây…"}
        className="scroll-thin min-h-0 flex-1 resize-none border-0 bg-transparent px-8 py-[26px] text-[17px] leading-[1.85] shadow-none outline-none ring-0 placeholder:text-muted/70 focus:outline-none focus:ring-0"
      />
      {exercise.task === "task1" ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-navy/8 px-6 py-3.5">
          <div className="flex items-baseline gap-4">
            <span>
              <b className="text-[30px] font-extrabold">{words}</b>
              <span className="text-muted"> / {info.minWords}</span>
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <span className="text-[13px] text-muted">{savedLine}</span>
            <SubmitButton disabled={!canSubmit} grading={grading} onClick={submit} compact />
          </div>
        </div>
      ) : (
        <div className="border-t border-navy/8 px-8 py-2.5 text-[13px] text-muted">{savedLine}</div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col gap-4 lg:h-[calc(100dvh-3.5rem)]">
      {live}
      {header}
      {timeUp && !grading && (
        <p role="alert" className="glass flex items-center gap-2.5 self-start rounded-full bg-white/55 py-2.5 pl-4 pr-5 text-[15px]">
          <ClockIcon size={18} className="shrink-0 text-status-rejected" />
          <b className="font-semibold text-status-rejected-text">Hết giờ.</b>
          <span className="text-muted">Bài đã khoá, bấm Nộp bài để chấm.</span>
        </p>
      )}
      {exercise.task === "task1" ? (
        <div className="flex min-h-0 flex-1 flex-col gap-5 lg:flex-row">
          <Task1Prompt exercise={exercise} />
          <section aria-label="Bài viết" className="flex min-h-0 min-w-0 flex-1 flex-col">
            {editor}
          </section>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-5 lg:flex-row">
          <section aria-label="Bài viết" className="flex min-h-0 min-w-0 flex-1 flex-col gap-3.5">
            <div className="glass rounded-[28px] px-[22px] py-4">
              <p className="text-base font-semibold leading-relaxed">{exercise.prompt}</p>
            </div>
            {editor}
          </section>
          <aside className="flex shrink-0 flex-col gap-4 lg:w-[280px]">
            <div className="glass flex flex-col gap-1.5 rounded-[28px] p-6">
              <span className="text-[13px] text-muted">Số từ</span>
              <div className="flex items-baseline gap-2">
                <b className="text-[44px] font-extrabold leading-none tracking-[-0.02em]">{words}</b>
                <span className="text-muted">/ {info.minWords}</span>
              </div>
              <div aria-hidden="true" className="h-1.5 rounded-full bg-navy/12">
                <div className="h-full rounded-full bg-orange" style={{ width: `${ratio * 100}%` }} />
              </div>
            </div>
            <div className="mt-auto flex flex-col gap-2">
              {blockedLine && (
                <p className="text-center text-[13px] text-status-spare-text">
                  {blockedLine}
                  {grader.state === "blocked" && (
                    <button type="button" onClick={recheckGrader} className="ml-1.5 font-semibold underline underline-offset-2">
                      Kiểm tra lại
                    </button>
                  )}
                </p>
              )}
              <SubmitButton disabled={!canSubmit} grading={grading} onClick={submit} />
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

function SubmitButton({ disabled, grading, onClick, compact = false }: { disabled: boolean; grading: boolean; onClick: () => void; compact?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-full bg-orange font-bold text-navy-deep shadow-[0_10px_24px_rgb(235_164_94/0.45)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none ${
        compact ? "min-h-12 px-8 text-base" : "min-h-14 w-full text-base"
      }`}
    >
      {grading ? "Đang chấm…" : "Nộp bài"}
    </button>
  );
}

function GradingOverlay() {
  return (
    <div role="status" className="absolute inset-0 z-10 grid place-items-center bg-white/35 backdrop-blur-[6px]">
      <div className="flex flex-col items-center gap-3.5 rounded-[20px] border border-white/75 bg-white/75 px-9 py-6">
        <b className="text-xl">Đang chấm bài</b>
        <div aria-hidden="true" className="h-2 w-[280px] overflow-hidden rounded-full bg-navy/12">
          <div className="animate-slide-bar h-full w-1/3 rounded-full bg-navy" />
        </div>
        <p className="text-[13px] text-muted">Vài phút. Đừng đóng trang.</p>
      </div>
    </div>
  );
}

/** Cột trái của Task 1: đề, biểu đồ (khối co theo chiều cao biểu đồ) và nút Phóng to. */
function Task1Prompt({ exercise }: { exercise: WritingExercise }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const chart = exercise.chart;

  return (
    // Vùng cuộn có card: bóng nhỏ và đệm 12px bù bằng margin âm (scroll-cards, globals.css); rộng 454 = card 430 + 2 × 12 đệm.
    <aside
      aria-label="Đề và biểu đồ"
      className="scroll-thin scroll-cards flex shrink-0 flex-col gap-3.5 lg:-mx-3 lg:-mt-2 lg:-mb-4 lg:w-[454px] lg:overflow-y-auto lg:px-3 lg:pt-2 lg:pb-4"
    >
      <div className="glass rounded-[28px] px-[22px] py-4">
        <p className="text-[15px] font-semibold leading-relaxed">{exercise.prompt}</p>
      </div>
      {chart && (
        <div className="glass-paper flex flex-col gap-2.5 rounded-[28px] px-5 py-[18px]">
          <div className="flex items-center justify-between gap-3">
            <b>{chart.unit}</b>
            <button
              type="button"
              aria-label="Phóng to biểu đồ và bảng số liệu"
              onClick={() => dialog.current?.showModal()}
              className="glass grid size-10 shrink-0 place-items-center rounded-full hover:bg-white/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
            >
              <ExpandIcon size={18} />
            </button>
          </div>
          <BarChart chart={chart} />
          <ChartLegend chart={chart} />
        </div>
      )}
      {chart && (
        <dialog
          ref={dialog}
          aria-labelledby="zoom-title"
          onClick={(e) => e.target === dialog.current && dialog.current.close()}
          className="scroll-thin m-auto max-h-[90dvh] w-[min(1040px,94vw)] rounded-[28px] border border-white/90 bg-white/92 p-0 text-navy-deep shadow-[0_30px_80px_rgb(33_61_104/0.3)] backdrop:bg-cream/40 backdrop:backdrop-blur-md"
        >
          <div className="flex flex-col gap-4 px-8 py-7">
            <div className="flex items-start justify-between gap-4">
              <h2 id="zoom-title" className="text-[22px] font-bold">
                Đề và biểu đồ
              </h2>
              <button
                type="button"
                aria-label="Đóng"
                onClick={() => dialog.current?.close()}
                className="glass grid size-10 shrink-0 place-items-center rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
              >
                <XIcon size={18} />
              </button>
            </div>
            <p className="text-base font-semibold leading-relaxed">{exercise.prompt}</p>
            <div className="grid grid-cols-1 items-start gap-5 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <div className="flex flex-col gap-2.5 rounded-[20px] border border-white/75 bg-white/60 px-[18px] py-4">
                <b>{chart.unit}</b>
                <BarChart chart={chart} large />
                <ChartLegend chart={chart} large />
              </div>
              <div className="rounded-[20px] border border-white/75 bg-white/60 px-2 py-3">
                <ChartTable chart={chart} />
              </div>
            </div>
          </div>
        </dialog>
      )}
    </aside>
  );
}
