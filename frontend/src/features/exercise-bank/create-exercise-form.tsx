"use client";

import { useId, useState, type FormEvent } from "react";
import { MinusIcon, PlusIcon, SparkleIcon } from "@/components/icons";
import type { CreateRequest } from "./create-job";
import { skillVisual } from "./skill-visual";

/** Giới hạn theo GenerateRequest (backend/ielts_agent/agents/uc04/models.py). */
const MIN_BAND = 1;
const MAX_BAND = 9;
const MIN_QUESTIONS = 8;
const MAX_QUESTIONS = 13;
const WORD_LIMITS = [1, 2, 3, 4, 5];
const MIN_TOPIC = 3;
const MAX_TOPIC = 200;

type CreateExerciseFormProps = {
  onCreate: (request: CreateRequest) => void;
  /** Đang chờ backend tạo bài: khoá nút để không gửi trùng (mỗi lần sinh tốn lượt gọi LLM). */
  busy?: boolean;
};

/** Form "Tạo bài mới" của người học: chỉ Reading/Listening (UC-04). */
export function CreateExerciseForm({ onCreate, busy = false }: CreateExerciseFormProps) {
  const [skill, setSkill] = useState<"reading" | "listening">("reading");
  const [topic, setTopic] = useState("");
  const [band, setBand] = useState(6);
  const [questionCount, setQuestionCount] = useState(10);
  const [wordLimit, setWordLimit] = useState(2);
  const limitId = useId();
  const topicOk = topic.trim().length >= MIN_TOPIC;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!topicOk || busy) return;
    onCreate({ skill, topic: topic.trim(), targetBand: band, questionCount, completionWordLimit: wordLimit });
    setTopic("");
  }

  const fieldLabel = "mb-2 block text-[13px] font-semibold text-muted";
  const field = "w-full rounded-2xl border-[1.5px] border-navy/20 bg-white/85 px-4 py-3 text-[15px] text-navy-deep outline-none focus:border-navy/50";

  return (
    <form onSubmit={submit} aria-labelledby="create-title" className="glass flex flex-col gap-4 rounded-[26px] p-5">
      <h2 id="create-title" className="flex items-center gap-2.5 text-base font-bold">
        <SparkleIcon size={20} className="text-[#e8963f]" />
        Tạo bài mới
      </h2>

      <div role="radiogroup" aria-label="Kỹ năng" className="flex gap-[3px] rounded-full bg-navy/10 p-1">
        {(["reading", "listening"] as const).map((s) => {
          const { icon: Icon } = skillVisual[s];
          const on = skill === s;
          return (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => setSkill(s)}
              className={`flex flex-1 items-center justify-center gap-2 rounded-full py-2 text-sm ${
                on ? "bg-cream font-semibold text-navy-deep shadow-[0_2px_8px_rgb(33_61_104/0.15)]" : "font-medium text-muted"
              }`}
            >
              <Icon size={15} />
              {s === "reading" ? "Reading" : "Listening"}
            </button>
          );
        })}
      </div>

      <input
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        maxLength={MAX_TOPIC}
        aria-label="Chủ đề"
        placeholder="Chủ đề"
        className={field}
      />

      <div className="grid grid-cols-2 gap-3">
        <Stepper
          label="Band"
          value={band}
          min={MIN_BAND}
          max={MAX_BAND}
          step={0.5}
          format={(v) => v.toFixed(1)}
          decreaseLabel="Giảm 0.5 band"
          increaseLabel="Tăng 0.5 band"
          onChange={setBand}
        />

        <Stepper
          label="Số câu"
          value={questionCount}
          min={MIN_QUESTIONS}
          max={MAX_QUESTIONS}
          step={1}
          format={String}
          decreaseLabel="Bớt một câu"
          increaseLabel="Thêm một câu"
          onChange={setQuestionCount}
        />
      </div>

      <div>
        <span id={limitId} className={fieldLabel}>
          Giới hạn từ ở câu điền
        </span>
        <div role="radiogroup" aria-labelledby={limitId} className="flex gap-1 rounded-2xl bg-navy/8 p-1">
          {WORD_LIMITS.map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={wordLimit === n}
              onClick={() => setWordLimit(n)}
              className={`flex-1 rounded-xl py-2 text-sm ${
                wordLimit === n ? "bg-navy font-bold text-cream" : "font-medium text-muted"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      <button
        type="submit"
        disabled={!topicOk || busy}
        className="rounded-full bg-orange py-3.5 text-[15px] font-bold text-navy-deep shadow-[0_10px_24px_rgb(235_164_94/0.45)] disabled:opacity-50 disabled:shadow-none"
      >
        {busy ? "Đang tạo bài…" : "Tạo bài"}
      </button>
    </form>
  );
}

type StepperProps = {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (value: number) => string;
  decreaseLabel: string;
  increaseLabel: string;
  onChange: (value: number) => void;
};

/** Ô chọn số bằng nút − / +, dùng cho Band (bước 0.5) và Số câu (bước 1). */
function Stepper({ label, value, min, max, step, format, decreaseLabel, increaseLabel, onChange }: StepperProps) {
  const labelId = useId();
  const button = "grid size-8 shrink-0 place-items-center rounded-full bg-white/85 disabled:opacity-40";
  return (
    <div>
      <span id={labelId} className="mb-2 block text-[13px] font-semibold text-muted">
        {label}
      </span>
      <div role="group" aria-labelledby={labelId} className="flex items-center justify-between gap-1 rounded-2xl bg-navy/8 p-1">
        <button
          type="button"
          aria-label={decreaseLabel}
          disabled={value <= min}
          onClick={() => onChange(Math.max(min, value - step))}
          className={button}
        >
          <MinusIcon size={15} />
        </button>
        <b className="text-base" aria-live="polite">
          {format(value)}
        </b>
        <button
          type="button"
          aria-label={increaseLabel}
          disabled={value >= max}
          onClick={() => onChange(Math.min(max, value + step))}
          className={button}
        >
          <PlusIcon size={15} />
        </button>
      </div>
    </div>
  );
}
