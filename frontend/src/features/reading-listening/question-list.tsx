"use client";

import { CheckIcon } from "@/components/icons";
import type { AttemptExercise, AttemptQuestion, AttemptQuestionGroup } from "@/lib/api/attempts";
import { choicesFor, groupedQuestions, instructionsShown, MAX_ANSWER_CHARS, stripRepeatedLimit } from "./questions";

type QuestionListProps = {
  exercise: AttemptExercise;
  answers: Record<string, string>;
  onChange: (questionId: string, value: string) => void;
  /** Đang chấm: khoá mọi ô. */
  disabled: boolean;
};

const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy";
/** Thẻ câu hỏi: bo 20px, đệm 12px; ô số câu bên trong bo 8px (20 − 12). */
const card = "glass-card relative flex gap-3 rounded-[20px] p-3";

/** Câu hỏi theo nhóm: chọn một (lựa chọn, T/F/NG) hoặc ô nhập chữ. Nhóm không có khung; mỗi câu là một thẻ. */
export function QuestionList({ exercise, answers, onChange, disabled }: QuestionListProps) {
  const groups = groupedQuestions(exercise);
  const shown = instructionsShown(groups);
  return (
    <div className="flex flex-col gap-3">
      {groups.map((group, i) => (
        // Nhóm nối tiếp cùng hướng dẫn trông như một nhóm; aria-label vẫn đọc hướng dẫn của nhóm.
        <section
          key={group.group_id}
          aria-label={group.instructions || "Nhóm câu hỏi"}
          className={`flex flex-col gap-3 ${shown[i] && i > 0 ? "mt-3" : ""}`}
        >
          {shown[i] && <p className="px-1 text-[15px] font-semibold leading-relaxed">{group.instructions}</p>}
          {group.questions.map((question) => (
            <QuestionItem
              key={question.id}
              group={group}
              question={question}
              value={answers[question.id] ?? ""}
              onChange={(value) => onChange(question.id, value)}
              disabled={disabled}
            />
          ))}
        </section>
      ))}
    </div>
  );
}

type QuestionItemProps = {
  group: AttemptQuestionGroup;
  question: AttemptQuestion;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
};

function QuestionItem({ group, question, value, onChange, disabled }: QuestionItemProps) {
  const answered = value.trim() !== "";
  const promptId = `q-${question.id}`;
  const prompt = stripRepeatedLimit(question.prompt, group.instructions);
  const badge = (
    <span
      className={`relative grid size-8 shrink-0 place-items-center rounded-lg text-[13px] font-bold ${
        answered ? "bg-navy text-cream" : "border border-navy/30 bg-white/70 text-navy"
      }`}
    >
      {question.number}
      {answered && (
        <CheckIcon size={12} strokeWidth={3} className="absolute -right-1 -top-1 rounded-full bg-orange p-0.5 text-navy-deep" />
      )}
    </span>
  );
  const status = <span className="sr-only">{answered ? "Đã trả lời." : "Chưa trả lời."}</span>;

  if (group.response_mode === "text") {
    return (
      <div className={card}>
        {badge}
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <label htmlFor={promptId} className="text-[15px] font-medium leading-relaxed">
            {prompt}
            {status}
          </label>
          <input
            id={promptId}
            type="text"
            value={value}
            maxLength={MAX_ANSWER_CHARS}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            className={`min-h-11 w-full rounded-[14px] border border-navy/20 bg-white px-3 text-[15px] ${focusRing} disabled:opacity-60`}
          />
        </div>
      </div>
    );
  }

  const choices = choicesFor(group, question);
  const inline = group.response_mode === "classification";
  return (
    <div className={card}>
      {badge}
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <span id={promptId} className="text-[15px] font-medium leading-relaxed">
          {prompt}
          {status}
        </span>
        <div role="radiogroup" aria-labelledby={promptId} className={inline ? "flex flex-wrap gap-2" : "flex flex-col gap-1.5"}>
          {choices.map((choice) => (
            <label
              key={choice.value}
              className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-[14px] border px-3 py-2 text-[15px] has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-navy ${
                value === choice.value ? "border-navy bg-navy/10 font-semibold" : "border-navy/15 bg-white/70 hover:bg-white"
              }`}
            >
              <input
                type="radio"
                name={promptId}
                value={choice.value}
                checked={value === choice.value}
                disabled={disabled}
                onChange={() => onChange(choice.value)}
                className="size-4 shrink-0 accent-navy"
              />
              {inline ? (
                choice.text
              ) : (
                <span>
                  <b className="mr-2">{choice.value}</b>
                  {choice.text}
                </span>
              )}
            </label>
          ))}
        </div>
        {answered && !disabled && (
          <button type="button" onClick={() => onChange("")} className={`self-start min-h-11 text-sm font-semibold text-muted underline underline-offset-2 hover:text-navy-deep ${focusRing}`}>
            Bỏ chọn
          </button>
        )}
      </div>
    </div>
  );
}
