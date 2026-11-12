"use client";

import { useMemo, useRef, useState, type ReactNode } from "react";
import { AttemptPicker } from "@/components/attempt-picker";
import { CheckIcon, MinusIcon, XIcon } from "@/components/icons";
import { formatDuration } from "@/features/writing/text";
import { WritingHeader } from "@/features/writing/writing-header";
import type { AttemptView, PracticeResult } from "@/lib/api/attempts";
import type { StoredAttempt } from "./attempt-store";
import { AudioPlayer } from "./audio-player";
import { audioOf } from "./audio-rules";
import { blockHighlights, splitBlocks } from "./blocks";
import { BlockParagraph, ScriptToggle } from "./paragraph";
import { choicesFor, groupedQuestions, stripRepeatedLimit } from "./questions";
import { countStatuses, defaultFilter, filterQuestions, reasonText, segmentForEvidence, statusOf, type AudioSegment, type QuestionFilter, type QuestionStatus } from "./result-view";
import { SplitPane } from "./split-pane";

type TestResultProps = {
  title: string;
  /** Chế độ và kỹ năng, hiện dưới tiêu đề. */
  meta: string[];
  back: { href: string; label: string };
  view: AttemptView;
  result: PracticeResult;
  /** Các lượt đã nộp của bài này, mới nhất trước. */
  attempts: StoredAttempt[];
  onSelect: (attempt: StoredAttempt) => void;
  onRedo: () => void;
  /** Vùng aria-live của màn làm bài. */
  live: ReactNode;
};

const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy";
const pill = `inline-flex min-h-11 items-center justify-center rounded-full border border-navy/25 bg-white/70 px-5 text-[15px] font-semibold hover:bg-white ${focusRing}`;
// Nút phụ trong ô câu hỏi: chữ gạch chân, thấp hơn trên màn rộng (chuột), đủ 44px trên màn cảm ứng.
const ghost = `inline-flex min-h-11 items-center rounded-full text-sm font-semibold text-navy min-[1150px]:min-h-8 ${focusRing}`;

/**
 * Trạng thái câu: biểu tượng trong vòng tròn, chữ cho trình đọc màn hình (sr-only) và title; ô số câu cùng màu.
 * Ba biểu tượng khác hình nhau nên vẫn phân biệt được khi trình duyệt ép màu (tương phản cao).
 */
const STATUS: Record<QuestionStatus, { label: string; icon: typeof CheckIcon; badge: string }> = {
  correct: { label: "Đúng", icon: CheckIcon, badge: "border-status-correct/40 bg-status-correct/12 text-status-correct-text" },
  wrong: { label: "Sai", icon: XIcon, badge: "border-status-rejected/40 bg-status-rejected/10 text-status-rejected-text" },
  blank: { label: "Bỏ trống", icon: MinusIcon, badge: "border-navy/20 bg-navy/5 text-muted" },
};
const FILTERS: { value: QuestionFilter; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "wrong", label: "Sai" },
  { value: "blank", label: "Bỏ trống" },
  { value: "correct", label: "Đúng" },
];
// Màn kết quả chỉ nghe lại: không lưu số lần nghe của lượt làm.
const FRESH_AUDIO = { plays: 0, finished: false, started: false };
const ignoreProgress = () => {};

/**
 * Màn kết quả Reading/Listening: hàng tóm tắt (lượt làm, số câu đúng), từng câu (Đúng/Sai/Bỏ trống) kèm đáp án và giải thích, lọc theo trạng thái,
 * "Xem bằng chứng" tô và cuộn tới chỗ trong bài đọc/script. Listening có trình phát nghe lại và script thu gọn mặc định.
 */
export function TestResult({ title, meta, back, view, result, attempts, onSelect, onRedo, live }: TestResultProps) {
  const listening = view.skill === "listening";
  const text = view.exercise.text;
  const speakerTurns = view.exercise.speakerTurns;
  const blocks = useMemo(() => splitBlocks(text, view.skill, speakerTurns), [text, view.skill, speakerTurns]);
  const counts = countStatuses(result.questions);
  const [filter, setFilter] = useState(() => defaultFilter(counts));
  const [shown, setShown] = useState<string | null>(null);
  const [scriptOpen, setScriptOpen] = useState(!listening);
  const [segment, setSegment] = useState<AudioSegment>();
  const passage = useRef<HTMLElement>(null);

  const byId = new Map(result.questions.map((q) => [q.question_id, q]));
  const visible = new Set(filterQuestions(result.questions, filter).map((q) => q.question_id));
  const audio = listening ? audioOf(view.exercise) : null;
  const ranges = blockHighlights(blocks, text, shown ? (byId.get(shown)?.evidence_span ?? null) : null);

  function toggleEvidence(questionId: string) {
    const next = shown === questionId ? null : questionId;
    setShown(next);
    if (!next) return;
    setScriptOpen(true);
    // Đợi vẽ lại (script vừa mở, phần vừa tô) rồi cuộn tới.
    requestAnimationFrame(() => {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      passage.current?.querySelector("mark")?.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    });
  }

  const left = (
    <>
      {listening && <AudioPlayer src={audio?.url ?? null} mode="practice" saved={FRESH_AUDIO} onProgress={ignoreProgress} segment={segment} />}
      {listening && <ScriptToggle open={scriptOpen} onToggle={() => setScriptOpen(!scriptOpen)} controls="result-script" />}
      {scriptOpen && (
        <section ref={passage} id="result-script" aria-label={listening ? "Script" : "Bài đọc"} className="glass-paper rounded-[28px] px-8 py-6">
          {blocks.map((block, i) => (
            <BlockParagraph key={block.start} label={block.label} text={block.text} range={ranges[i]} />
          ))}
        </section>
      )}
    </>
  );

  const right = (
    <>
      <div role="group" aria-label="Lọc câu theo kết quả" className="glass flex flex-wrap gap-1 self-start rounded-[20px] p-1">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={filter === f.value}
            onClick={() => {
              setFilter(f.value);
              setShown(null);
            }}
            className={`min-h-11 rounded-[16px] px-3 text-sm font-semibold ${focusRing} ${filter === f.value ? "bg-navy text-cream shadow-sm" : "hover:bg-white/60"}`}
          >
            {f.label} ({counts[f.value]})
          </button>
        ))}
      </div>
      <ol aria-label="Kết quả từng câu" className="flex flex-col gap-3">
        {visible.size === 0 && <li className="px-1 text-sm text-muted">Không có câu nào.</li>}
        {groupedQuestions(view.exercise).flatMap((group) =>
          group.questions.map((question) => {
            const q = byId.get(question.id);
            if (!q || !visible.has(q.question_id)) return null;
            const status = statusOf(q);
            const { label, icon: Icon, badge } = STATUS[status];
            const reason = reasonText(q.reason);
            const choices = group.response_mode === "classification" ? [] : choicesFor(group, question);
            // Trắc nghiệm, matching: hiện cả nhãn và nội dung lựa chọn.
            const full = (value: string) => {
              const choice = choices.find((c) => c.value.trim().toLowerCase() === value.trim().toLowerCase());
              return choice ? `${choice.value}. ${choice.text}` : value;
            };
            const hasEvidence = !!q.evidence_span?.trim() && text.includes(q.evidence_span);
            const replay = audio ? segmentForEvidence(audio.turns, text, q.evidence_span) : null;
            const pressed = shown === q.question_id;
            return (
              <li key={q.question_id} className="glass-card flex gap-3 rounded-[20px] p-3">
                <span className={`grid size-8 shrink-0 place-items-center rounded-lg border text-[13px] font-bold ${badge}`}>{question.number}</span>
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-[15px] font-medium leading-snug">{stripRepeatedLimit(question.prompt, group.instructions)}</p>
                    <span title={label} className={`grid size-6 shrink-0 place-items-center rounded-full border ${badge}`}>
                      <Icon size={14} strokeWidth={3} />
                      <span className="sr-only">{label}</span>
                    </span>
                  </div>
                  {reason && <p className="text-sm text-status-rejected-text">{reason}</p>}
                  <dl className="grid grid-cols-2 gap-x-4 text-[15px] leading-snug">
                    <div className="min-w-0">
                      <dt className="text-xs text-muted">Bạn trả lời</dt>
                      <dd className={`break-words ${status === "wrong" ? "text-muted line-through decoration-status-rejected/60" : ""}`}>
                        {status === "blank" ? "—" : full(q.response)}
                      </dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-xs text-muted">Đáp án đúng</dt>
                      <dd className="break-words font-semibold">{full(q.correct_answer)}</dd>
                    </div>
                  </dl>
                  <p className="text-sm leading-snug text-muted">
                    <span className="mr-2 text-xs font-semibold text-navy-deep">Giải thích</span>
                    {q.explanation}
                  </p>
                  {(hasEvidence || replay) && (
                    <div className="flex flex-wrap gap-x-4">
                      {hasEvidence && (
                        <button
                          type="button"
                          aria-pressed={pressed}
                          onClick={() => toggleEvidence(q.question_id)}
                          className={`${ghost} ${pressed ? "bg-orange/40 px-3 text-navy-deep" : "underline underline-offset-2"}`}
                        >
                          {pressed ? "Đang tô bằng chứng" : "Xem bằng chứng"}
                        </button>
                      )}
                      {replay && (
                        <button type="button" onClick={() => setSegment({ ...replay })} className={`${ghost} underline underline-offset-2`}>
                          Nghe lại đoạn này
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </li>
            );
          }),
        )}
      </ol>
    </>
  );

  return (
    <div className="flex flex-col gap-4 min-[1150px]:h-[calc(100dvh-3.5rem)]">
      {live}
      <WritingHeader title={title} meta={[...meta, formatDuration(view.elapsed_seconds)]} skill={view.skill} back={back} />

      {/* Màn rộng giữ một hàng: nhiều lượt thì hàng chọn lượt tự cuộn ngang. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 min-[1150px]:flex-nowrap">
        {attempts.length > 1 && (
          <AttemptPicker
            attempts={attempts.map((a) => ({ id: a.attemptId, value: a.score ?? "—", savedAt: a.savedAt }))}
            activeId={view.attempt_id}
            valueLabel="đúng"
            onSelect={(id) => {
              const target = attempts.find((a) => a.attemptId === id);
              if (target && id !== view.attempt_id) onSelect(target);
            }}
          />
        )}
        <p className="shrink-0 font-bold" title={`Cách chấm: ${result.grading_version}`}>
          <span className="text-xl">
            {result.raw_score}/{result.total_questions}
          </span>{" "}
          câu đúng
        </p>
        {result.band !== null && <p className="shrink-0 font-bold">Band {result.band.toFixed(1)}</p>}
        <button type="button" onClick={onRedo} className={`${pill} ml-auto shrink-0`}>
          Làm lại
        </button>
      </div>

      <SplitPane left={left} right={right} leftClass="gap-3" rightClass="gap-3" />
    </div>
  );
}
