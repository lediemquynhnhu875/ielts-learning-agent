import { CheckIcon, XIcon } from "@/components/icons";
import { formatDateTime } from "@/lib/format";
import { DEDUP_THRESHOLD, type GenerationMetadata, type Verification } from "@/mock-data/reading-listening";

type Stage = { name: string; description: string; passed: boolean; result: string };

/** 5 chặng kiểm chứng UC-04, theo thứ tự trong agents/uc04/agent.py. */
function stages(v: Verification, skill: "reading" | "listening"): Stage[] {
  const dedupPassed = v.maxSimilarity <= DEDUP_THRESHOLD;
  return [
    { name: "An toàn", description: "Chủ đề và nội dung phù hợp", passed: v.safetyPassed, result: v.safetyPassed ? "Đạt" : "Không đạt" },
    {
      name: "Sinh bài",
      description: skill === "reading" ? "Tạo bài đọc và câu hỏi" : "Tạo script và câu hỏi",
      passed: true,
      result: `Lần ${v.attempts}`,
    },
    { name: "Quy tắc", description: "Code kiểm độ dài, đáp án, bằng chứng", passed: v.rulesPassed, result: v.rulesPassed ? "Đạt" : "Không đạt" },
    {
      name: "Solver",
      description: "AI khác làm bài, không thấy đáp án",
      passed: true,
      result: `${v.solverRetained}/${v.solverGenerated}`,
    },
    { name: "Trùng lặp", description: "So với các bài trong kho", passed: dedupPassed, result: dedupPassed ? "Đạt" : "Không đạt" },
  ];
}

export function VerificationPanel({ verification, skill }: { verification: Verification; skill: "reading" | "listening" }) {
  const list = stages(verification, skill);
  return (
    <section aria-label="Các chặng kiểm chứng" className="glass rounded-[26px] px-6 py-5">
      <ol>
        {list.map((stage, i) => (
          <li key={stage.name} className={`relative flex items-start gap-3.5 ${i < list.length - 1 ? "pb-5" : ""}`}>
            {i < list.length - 1 && (
              <span aria-hidden="true" className="absolute bottom-0 left-[15px] top-9 w-0.5 bg-navy/22" />
            )}
            <span
              className={`relative grid size-8 shrink-0 place-items-center rounded-full text-cream ${
                stage.passed ? "bg-navy" : "bg-status-rejected"
              }`}
            >
              {stage.passed ? <CheckIcon size={16} strokeWidth={2.4} /> : <XIcon size={15} strokeWidth={2.4} />}
            </span>
            <div className="min-w-0 flex-1 leading-snug">
              <b className="text-[15px] font-semibold">{stage.name}</b>
              <div className="mt-0.5 text-[13px] text-muted">{stage.description}</div>
            </div>
            <b className={`pt-1 text-[15px] ${stage.passed ? "text-navy" : "text-status-rejected-text"}`}>{stage.result}</b>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Thẻ "Giống bài khác nhất": cosine lớn nhất với các bài verified, vạch ngưỡng 0.9. */
export function SimilarityPanel({ verification }: { verification: Verification }) {
  const value = verification.maxSimilarity;
  return (
    <section aria-label="Giống bài khác nhất" className="glass rounded-[26px] px-6 py-5">
      <div className="flex items-baseline justify-between">
        <b className="text-[15px]">Giống bài khác nhất</b>
        <b className="text-[22px]">{value.toFixed(2)}</b>
      </div>
      <div
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={value}
        aria-label={`Độ giống ${value.toFixed(2)}, ngưỡng ${DEDUP_THRESHOLD}`}
        className="relative mt-3.5 h-3.5 rounded-full bg-navy/12"
      >
        <div className="h-full rounded-full bg-navy" style={{ width: `${value * 100}%` }} />
        <div
          className="absolute -bottom-1.5 -top-1.5 w-[3px] rounded-sm bg-status-rejected"
          style={{ left: `${DEDUP_THRESHOLD * 100}%` }}
        />
      </div>
      <div className="relative mt-1.5 h-[18px] text-xs text-muted">
        <span className="absolute left-0">0</span>
        <span
          className="absolute -translate-x-1/2 font-bold text-status-rejected-text"
          style={{ left: `${DEDUP_THRESHOLD * 100}%` }}
        >
          {DEDUP_THRESHOLD}
        </span>
      </div>
      <div className="mt-1.5 text-[13px] text-muted">
        Gần nhất:{" "}
        {verification.nearestItemTitle ? (
          <b className="font-semibold text-navy">{verification.nearestItemTitle}</b>
        ) : (
          "chưa có bài để so"
        )}
      </div>
    </section>
  );
}

/** Chip Sinh / Solver / Tạo: model sinh bài, model solver, thời điểm tạo. */
export function MetadataChips({ metadata, createdAt }: { metadata: GenerationMetadata; createdAt: string }) {
  const chips = [
    { label: "Sinh", value: metadata.model, title: metadata.promptVersion },
    { label: "Solver", value: metadata.solverModel, title: metadata.solverPromptVersion },
    { label: "Tạo", value: formatDateTime(createdAt), title: undefined },
  ];
  return (
    <ul className="flex flex-wrap gap-2 px-1">
      {chips.map((c) => (
        <li key={c.label} title={c.title} className="glass inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[13px]">
          <span className="text-muted">{c.label}</span>
          <span className="font-medium">{c.value}</span>
        </li>
      ))}
    </ul>
  );
}
