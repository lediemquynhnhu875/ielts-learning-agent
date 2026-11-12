"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { WritingHeader } from "@/features/writing/writing-header";
import { createAttempt, getAttempt, saveAnswers, submitAttempt, type AttemptView, type PracticeResult } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/errors";
import { loadListeningExtras, type ListeningExtras } from "@/lib/api/listening";
import {
  addAttempt,
  pickAttempt,
  readAttempts,
  removeAttempt,
  updateAttempt,
  writeAttempts,
  type StoredAttempt,
  type TestMode,
} from "./attempt-store";
import { createAnswerDraft, MAX_PER_REQUEST, type AnswerDraft, type SaveStatus } from "./answer-draft";
import { AudioPlayer } from "./audio-player";
import { audioOf, scriptVisibility, type SavedAudio } from "./audio-rules";
import { splitBlocks } from "./blocks";
import { BlockParagraph, ScriptToggle } from "./paragraph";
import type { Playable } from "./playable";
import { QuestionList } from "./question-list";
import { chunkAnswers, questionIds, toAnswerMap, unansweredCount } from "./questions";
import { SplitPane } from "./split-pane";
import { TestResult } from "./test-result";

type Phase =
  | { name: "loading" }
  | { name: "doing"; view: AttemptView; stored: StoredAttempt; grading: boolean }
  | { name: "result"; view: AttemptView; result: PracticeResult; stored: StoredAttempt; attempts: StoredAttempt[] }
  | { name: "error"; message: string; retry: () => void };

const modeLabel: Record<TestMode, string> = { practice: "Luyện tập", mock: "Thi thử" };
const skillLabel = { reading: "Reading", listening: "Listening" } as const;

const messageOf = (error: unknown) => (error instanceof ApiError ? error.message : "Lỗi không xác định.");
const isSubmittedError = (error: unknown) => error instanceof ApiError && error.code === "attempt_submitted";

const pillButton =
  "inline-flex min-h-11 items-center justify-center rounded-full px-6 text-[15px] font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy disabled:cursor-not-allowed disabled:opacity-50";
const orangeButton = `${pillButton} bg-orange font-bold text-navy-deep shadow-lg shadow-orange/45 disabled:shadow-none`;
const notice = "glass self-start rounded-full bg-white/55 px-5 py-2 text-sm";
const NO_EXTRAS: ListeningExtras = { audio: null, turns: null };

/**
 * Màn làm bài Reading/Listening, dùng chung cho Luyện (/exercises/[id]) và Thi (/mock/[id]).
 * Mở màn là vào làm: có lượt chưa nộp đã lưu thì mở lại, không có thì tạo lượt mới (đúng một lần mỗi lần mở).
 * Pha: Đang làm → Đang chấm → Kết quả (test-result.tsx), kèm Lỗi. Lượt làm và token lưu trong trình duyệt (attempt-store).
 */
export function TestSession({ exercise, mode }: { exercise: Playable; mode: TestMode }) {
  const [phase, setPhase] = useState<Phase>({ name: "loading" });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [save, setSave] = useState<{ status: SaveStatus; message: string | null } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [scriptOpen, setScriptOpen] = useState(false);
  // Listening: lượt người nói và audio đã kiểm chứng lấy riêng (GET attempts/{id} chưa có). `undefined` là đang lấy.
  const [extras, setExtras] = useState<ListeningExtras | undefined>(exercise.skill === "listening" ? undefined : NO_EXTRAS);
  const draft = useRef<AnswerDraft | null>(null);
  const opened = useRef<string | null>(null);
  const busy = useRef(false);
  const confirm = useRef<HTMLDialogElement>(null);

  const basePath = mode === "mock" ? `/mock/${exercise.id}` : `/exercises/${exercise.id}`;
  const back = mode === "mock" ? { href: "/mock", label: "Quay lại Thi thử" } : { href: "/exercises", label: "Quay lại Kho đề" };

  const patchStored = (attemptId: string, patch: Parameters<typeof updateAttempt>[2]) =>
    writeAttempts(mode, exercise.id, updateAttempt(readAttempts(mode, exercise.id), attemptId, patch));

  function show(next: AttemptView, stored: StoredAttempt) {
    draft.current?.close();
    draft.current = null;
    if (next.status === "submitted" && next.result) {
      // Lưu số câu đúng theo lượt để hàng chọn lượt hiện được mà không phải hỏi backend từng lượt.
      const score = `${next.result.raw_score}/${next.result.total_questions}`;
      if (!stored.submitted || stored.score !== score) patchStored(stored.attemptId, { submitted: true, score });
      const attempts = readAttempts(mode, exercise.id).filter((a) => a.submitted);
      setPhase({ name: "result", view: next, result: next.result, stored: { ...stored, submitted: true, score }, attempts });
      return;
    }
    setAnswers(next.answers);
    setSave(null);
    draft.current = createAnswerDraft({
      save: (batch) => saveAnswers(next.attempt_id, stored.token, batch),
      onStatus: (status, error) => {
        // Lượt đã nộp ở nơi khác (tab khác): đọc lại và hiện kết quả.
        if (isSubmittedError(error)) void reopen(stored);
        else setSave({ status, message: error === undefined ? null : messageOf(error) });
      },
    });
    setPhase({ name: "doing", view: next, stored, grading: false });
  }

  async function reopen(stored: StoredAttempt) {
    try {
      show(await getAttempt(stored.attemptId, stored.token), stored);
    } catch (error) {
      setPhase({ name: "error", message: messageOf(error), retry: () => void reopen(stored) });
    }
  }

  /** Tạo lượt mới (một request). Khoá bằng `busy` để bấm nhanh hay effect chạy lại không tạo hai lượt. */
  async function begin() {
    if (busy.current) return;
    busy.current = true;
    setPhase({ name: "loading" });
    try {
      await create();
    } finally {
      busy.current = false;
    }
  }

  async function create() {
    try {
      const { attempt_token, ...created } = await createAttempt(exercise.id);
      const stored: StoredAttempt = { attemptId: created.attempt_id, token: attempt_token, plays: 0, finished: false, started: false, submitted: false, savedAt: Date.now() };
      writeAttempts(mode, exercise.id, addAttempt(readAttempts(mode, exercise.id), stored));
      show(created, stored);
    } catch (error) {
      setPhase({ name: "error", message: messageOf(error), retry: () => void begin() });
    }
  }

  /** Mở màn: một GET lượt đã lưu, hoặc một POST tạo lượt mới. GET báo 404 hoặc lượt đã nộp ở nơi khác thì tạo mới. */
  async function open(options: { redo: boolean; wantResult: boolean }) {
    if (busy.current) return;
    busy.current = true;
    try {
      const target = pickAttempt(readAttempts(mode, exercise.id), options);
      if (target) {
        try {
          const next = await getAttempt(target.attemptId, target.token);
          if (next.item_id === exercise.id && (next.status === "in_progress" || options.wantResult)) {
            show(next, target);
            return;
          }
          if (next.status === "submitted") patchStored(target.attemptId, { submitted: true });
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) {
            setPhase({ name: "error", message: messageOf(error), retry: () => void open(options) });
            return;
          }
          writeAttempts(mode, exercise.id, removeAttempt(readAttempts(mode, exercise.id), target.attemptId));
        }
      }
      await create();
    } finally {
      busy.current = false;
    }
  }

  // localStorage chỉ đọc sau khi gắn vào trình duyệt. `?redo=1`: lượt mới; `?view=result`: lượt đã nộp gần nhất.
  // Xoá tham số bằng history.replaceState (router.replace sẽ tải lại trang server và đọc bài thêm lần nữa).
  // Màn được hiện lại (Activity) mà không có tham số thì giữ nguyên trạng thái, không mở lại.
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      const search = new URLSearchParams(window.location.search);
      const redo = search.has("redo");
      const wantResult = search.get("view") === "result";
      if (redo || search.has("view")) window.history.replaceState(null, "", basePath);
      const key = `${mode}:${exercise.id}`;
      if (opened.current === key && !redo && !wantResult) return;
      opened.current = key;
      void open({ redo, wantResult });
    });
    return () => {
      cancelled = true;
    };
    // open/basePath đọc mode và exercise qua closure; chỉ chạy lại khi bài hoặc chế độ đổi.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exercise.id, mode]);

  // Lấy một lần mỗi bài. Lỗi (409 chưa kiểm chứng, 404, mạng) đã đổi thành "không có" trong loadListeningExtras.
  useEffect(() => {
    if (exercise.skill !== "listening") return;
    let cancelled = false;
    void loadListeningExtras(exercise.id).then((loaded) => {
      if (!cancelled) setExtras(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [exercise.id, exercise.skill]);

  // Rời trang: gửi nốt thay đổi đang chờ.
  useEffect(() => () => void draft.current?.flush(), []);

  function change(questionId: string, value: string) {
    setAnswers((current) => ({ ...current, [questionId]: value }));
    draft.current?.change(questionId, value);
  }

  function saveProgress(stored: StoredAttempt, progress: SavedAudio) {
    patchStored(stored.attemptId, progress);
    setPhase((current) => (current.name === "doing" ? { ...current, stored: { ...current.stored, ...progress } } : current));
  }

  async function submit(target: AttemptView, stored: StoredAttempt, all: Record<string, string>) {
    draft.current?.close();
    setPhase({ name: "doing", view: target, stored, grading: true });
    setAnnouncement("Đang chấm bài.");
    const map = toAnswerMap(questionIds(target.exercise), all);
    try {
      let body = map;
      // Nộp nhận tối đa 40 câu: bài dài hơn thì lưu theo lô rồi nộp không kèm đáp án.
      if (Object.keys(map).length > MAX_PER_REQUEST) {
        for (const chunk of chunkAnswers(map)) await saveAnswers(target.attempt_id, stored.token, chunk);
        body = {};
      }
      show(await submitAttempt(target.attempt_id, stored.token, body), stored);
      setAnnouncement("Đã chấm xong.");
    } catch (error) {
      if (isSubmittedError(error)) {
        await reopen(stored);
        return;
      }
      setAnnouncement("Chưa nộp được bài.");
      setPhase({ name: "error", message: messageOf(error), retry: () => void submit(target, stored, all) });
    }
  }

  const live = (
    <p aria-live="polite" className="sr-only">
      {announcement}
    </p>
  );
  const meta = [modeLabel[mode], skillLabel[exercise.skill]];

  // Chờ cả phần Listening: ở chế độ Thi không được lộ nút "Xem script" trước khi biết bài có audio hay không.
  if (phase.name === "loading" || phase.name === "error" || extras === undefined) {
    return (
      <div className="flex flex-col gap-4">
        {live}
        <WritingHeader title={exercise.title} meta={meta} skill={exercise.skill} back={back} />
        {phase.name !== "error" ? (
          <div aria-busy="true" aria-label="Đang mở bài" className="glass h-40 animate-pulse rounded-[32px] motion-reduce:animate-none" />
        ) : (
          <section role="alert" className="glass flex flex-col items-start gap-3 rounded-[32px] px-8 py-8">
            <h2 className="text-2xl font-extrabold tracking-tight">Có lỗi</h2>
            <p className="text-[15px] text-muted">{phase.message}</p>
            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={phase.retry} className={`${pillButton} bg-navy text-cream`}>
                Thử lại
              </button>
              <Link href={back.href} className={`${pillButton} border border-navy/25 bg-white/70 hover:bg-white`}>
                {mode === "mock" ? "Về Thi thử" : "Về Kho đề"}
              </Link>
            </div>
          </section>
        )}
      </div>
    );
  }

  // Gắn audio và lượt người nói vào bài, đúng chỗ audioOf và splitBlocks đọc.
  const withExtras = (view: AttemptView): AttemptView => ({
    ...view,
    exercise: { ...view.exercise, audio: extras.audio ?? undefined, speakerTurns: extras.turns },
  });

  if (phase.name === "result") {
    return (
      // key: đổi lượt thì bỏ phần bằng chứng đang tô của lượt trước.
      <TestResult
        key={phase.view.attempt_id}
        title={exercise.title}
        meta={meta}
        back={back}
        view={withExtras(phase.view)}
        result={phase.result}
        attempts={phase.attempts}
        onSelect={(stored) => {
          setAnnouncement("Đang mở lượt làm.");
          void reopen(stored);
        }}
        onRedo={() => void begin()}
        live={live}
      />
    );
  }

  const { stored, grading } = phase;
  const attempt = withExtras(phase.view);
  const ids = questionIds(attempt.exercise);
  const empty = unansweredCount(ids, answers);
  const listening = attempt.skill === "listening";
  const audio = listening ? audioOf(attempt.exercise) : null;
  // Reading luôn hiện bài đọc; nút Xem script và băng báo chưa có audio chỉ áp cho Listening.
  const script = listening ? scriptVisibility(mode, audio !== null, false) : { available: true, noAudioNotice: false };
  const saveLine =
    save === null
      ? "Tự lưu khi bạn trả lời"
      : save.status === "saved"
        ? "Đã lưu"
        : save.status === "error"
          ? `Lưu lỗi: ${save.message}`
          : "Đang lưu…";

  return (
    <div className="flex flex-col gap-4 min-[1150px]:h-[calc(100dvh-3.5rem)]">
      {live}
      <WritingHeader title={exercise.title} meta={[...meta, `${ids.length} câu`]} skill={exercise.skill} back={back} />
      <SplitPane
        leftClass="gap-3"
        rightClass="gap-4"
        left={
          <>
            {listening && mode === "mock" && audio && <p className={notice}>Audio chỉ nghe một lần, không tua.</p>}
            {listening && (
              <AudioPlayer
                src={audio?.url ?? null}
                mode={mode}
                saved={{ plays: stored.plays, finished: stored.finished, started: stored.started }}
                onProgress={(progress) => saveProgress(stored, progress)}
              />
            )}
            {script.noAudioNotice && (
              <p role="note" className={notice}>
                Chưa có audio, tạm làm bằng script
              </p>
            )}
            {listening && script.available && <ScriptToggle open={scriptOpen} onToggle={() => setScriptOpen(!scriptOpen)} controls="doing-script" />}
            {script.available && (!listening || scriptOpen) && (
              <section id="doing-script" aria-label={listening ? "Script" : "Bài đọc"} className="glass-paper rounded-[28px] px-8 py-6">
                {splitBlocks(attempt.exercise.text, attempt.skill, attempt.exercise.speakerTurns).map((block) => (
                  <BlockParagraph key={block.start} label={block.label} text={block.text} range={null} />
                ))}
              </section>
            )}
          </>
        }
        right={
          <>
            <QuestionList exercise={attempt.exercise} answers={answers} onChange={change} disabled={grading} />
            {/* -bottom-4 bằng đệm dưới của cột: thanh dính sát mép vùng cuộn, không lộ card cuộn bên dưới. */}
            <div className="glass sticky bottom-0 flex flex-wrap items-center justify-between gap-3 rounded-[24px] px-5 py-3 min-[1150px]:-bottom-4">
              <p aria-live="polite" className="flex min-w-0 flex-wrap items-center gap-2 text-sm text-muted">
                <span className={save?.status === "error" ? "text-status-rejected-text" : ""}>{saveLine}</span>
                {save?.status === "error" && (
                  <button
                    type="button"
                    onClick={() => void draft.current?.retry()}
                    className="min-h-11 font-semibold text-navy underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-navy"
                  >
                    Thử lại
                  </button>
                )}
              </p>
              <button type="button" disabled={grading} onClick={() => confirm.current?.showModal()} className={orangeButton}>
                {grading ? "Đang chấm…" : "Nộp bài"}
              </button>
            </div>
          </>
        }
      />

      <dialog
        ref={confirm}
        aria-labelledby="submit-title"
        className="m-auto w-[min(440px,calc(100vw-32px))] rounded-[28px] border border-white/90 bg-white/92 p-0 text-navy-deep shadow-2xl shadow-navy/30 backdrop:bg-cream/40 backdrop:backdrop-blur-md"
      >
        <div className="flex flex-col gap-3 px-7 py-6">
          <h2 id="submit-title" className="text-xl font-bold">
            Nộp bài?
          </h2>
          <p className="text-[15px] text-muted">
            {empty > 0 ? `Còn ${empty} câu chưa trả lời.` : "Bạn đã trả lời hết các câu."} Nộp rồi thì không sửa được.
          </p>
          <div className="mt-2 flex flex-wrap justify-end gap-3">
            <button type="button" onClick={() => confirm.current?.close()} className={`${pillButton} border border-navy/25 bg-white hover:bg-cream`}>
              Làm tiếp
            </button>
            <button
              type="button"
              disabled={grading}
              onClick={() => {
                confirm.current?.close();
                void submit(attempt, stored, answers);
              }}
              className={orangeButton}
            >
              Nộp bài
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
}
