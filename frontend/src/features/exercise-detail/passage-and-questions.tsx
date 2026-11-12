"use client";

import { useState } from "react";
import { Paragraph, splitParagraphs } from "@/features/reading-listening/paragraph";
import { questionKindLabel, type MockQuestion, type QuestionKind, type ReadingListeningExercise } from "@/mock-data/reading-listening";

const PREVIEW_PARAGRAPHS = 2;
const PREVIEW_QUESTIONS = 5;

type FlatQuestion = MockQuestion & { kind: QuestionKind };

/**
 * Bài đọc (hoặc script) và danh sách câu hỏi.
 * Mở một câu thì bằng chứng của câu đó được tô cam trong bài.
 */
export function PassageAndQuestions({ exercise }: { exercise: ReadingListeningExercise }) {
  const questions: FlatQuestion[] = exercise.questionGroups.flatMap((g) =>
    g.questions.map((q) => ({ ...q, kind: g.questionType })),
  );
  const [openNumber, setOpenNumber] = useState<number | null>(questions[0]?.number ?? null);
  const [fullText, setFullText] = useState(false);
  const [allQuestions, setAllQuestions] = useState(false);

  const openQuestion = questions.find((q) => q.number === openNumber);
  const highlight = openQuestion?.evidenceSpan ?? null;
  const paragraphs = splitParagraphs(exercise.text);
  const highlightIndex = highlight ? paragraphs.findIndex((p) => p.includes(highlight)) : -1;
  const shownParagraphs = fullText ? paragraphs : paragraphs.slice(0, Math.max(PREVIEW_PARAGRAPHS, highlightIndex + 1));
  const hiddenParagraphs = paragraphs.length - shownParagraphs.length;
  const shownQuestions = allQuestions ? questions : questions.slice(0, PREVIEW_QUESTIONS);
  const hiddenQuestions = questions.length - shownQuestions.length;

  return (
    <div className="flex flex-col gap-5">
      <section
        aria-label={exercise.skill === "reading" ? "Bài đọc" : "Script"}
        className="glass relative overflow-hidden rounded-[26px] bg-white/70 px-7 py-6"
      >
        {shownParagraphs.map((paragraph, i) => (
          <Paragraph key={i} text={paragraph} highlight={highlight} faded={!fullText && hiddenParagraphs > 0 && i === shownParagraphs.length - 1} />
        ))}
        {hiddenParagraphs > 0 ? (
          <div className="mt-3 flex justify-center">
            <button
              type="button"
              onClick={() => setFullText(true)}
              className="rounded-full bg-navy px-5 py-2 text-sm font-semibold text-cream"
            >
              Xem hết bài
            </button>
          </div>
        ) : (
          fullText &&
          paragraphs.length > PREVIEW_PARAGRAPHS && (
            <div className="mt-3 flex justify-center">
              <button type="button" onClick={() => setFullText(false)} className="text-sm font-semibold text-muted">
                Thu gọn
              </button>
            </div>
          )
        )}
      </section>

      <section aria-label="Câu hỏi" className="glass flex flex-col gap-2.5 rounded-[26px] p-4">
        {questions.length === 0 && (
          <p className="px-2 py-6 text-center text-sm text-muted">Dữ liệu giả lập chưa có câu hỏi cho bài này</p>
        )}
        {shownQuestions.map((q) => {
          const open = q.number === openNumber;
          return (
            <div key={q.number} className={`rounded-[18px] border border-white/90 ${open ? "bg-white/85" : "bg-white/50"}`}>
              <button
                type="button"
                aria-expanded={open}
                onClick={() => setOpenNumber(open ? null : q.number)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left"
              >
                <span className="grid size-8 shrink-0 place-items-center rounded-[11px] bg-navy text-[13px] font-bold text-cream">
                  {q.number}
                </span>
                <span className={`min-w-0 flex-1 text-[15px] font-medium ${open ? "" : "truncate"}`}>{q.prompt}</span>
                <span className="shrink-0 text-xs font-semibold text-muted">{questionKindLabel[q.kind]}</span>
                <span className="shrink-0 whitespace-nowrap rounded-full bg-navy/13 px-3 py-1 text-sm font-bold text-navy">
                  {q.answer}
                </span>
              </button>
              {open && (
                <div className="mx-4 mb-3.5 rounded-[14px] bg-orange/22 px-3.5 py-2.5 text-sm leading-relaxed">
                  {q.evidenceSpan ? `“${q.evidenceSpan}”` : <span className="text-muted">Không có bằng chứng trong bài</span>}
                </div>
              )}
            </div>
          );
        })}
        {hiddenQuestions > 0 && (
          <button
            type="button"
            onClick={() => setAllQuestions(true)}
            className="py-1.5 text-center text-sm font-semibold text-muted hover:text-navy-deep"
          >
            Xem thêm {hiddenQuestions} câu
          </button>
        )}
      </section>
    </div>
  );
}
