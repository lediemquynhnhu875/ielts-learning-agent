import type { ReactNode } from "react";
import type { SpeakingExercise } from "@/mock-data/speaking";
import { DetailHeader } from "./detail-header";
import { InfoPanel } from "./info-panel";

/** Trang chi tiết bộ đề Speaking cho quản trị (màn 10 trong mock). */
export function SpeakingDetail({ exercise }: { exercise: SpeakingExercise }) {
  const { part1, part2, part3 } = exercise;

  return (
    <div className="flex flex-col gap-5">
      <DetailHeader
        skill="speaking"
        title={part2.cue}
        status={exercise.status}
        meta={
          <>
            <b className="text-navy-deep">Band {exercise.targetBand?.toFixed(1) ?? "–"}</b>
            <span>Part 1–3</span>
          </>
        }
      />
      <div className="grid grid-cols-1 items-start gap-5 min-[1150px]:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col gap-5">
          <PartCard part="Part 1">
            <QuestionList items={part1} />
          </PartCard>

          <PartCard part="Part 2">
            <div className="rounded-[18px] bg-orange/22 px-5 py-4">
              <b className="text-[17px] leading-snug">{part2.cue}</b>
              {part2.points.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-sm text-muted">
                  {part2.points.map((point) => (
                    <li key={point} className="mt-1">
                      {point}
                    </li>
                  ))}
                </ul>
              )}
              {part2.explain && <div className="mt-2 text-sm text-muted">{part2.explain}</div>}
            </div>
          </PartCard>

          <PartCard part="Part 3">
            <QuestionList items={part3} />
          </PartCard>
        </div>
        <InfoPanel item={exercise} />
      </div>
    </div>
  );
}

function PartCard({ part, children }: { part: string; children: ReactNode }) {
  return (
    <section aria-label={part} className="glass rounded-[26px] bg-white/70 px-6 pb-3 pt-5">
      <span className="mb-3 inline-flex rounded-full bg-skill-speaking px-3 py-1 text-xs font-semibold text-cream">{part}</span>
      {children}
    </section>
  );
}

function QuestionList({ items }: { items: string[] }) {
  return (
    <ol>
      {items.map((q) => (
        <li key={q} className="border-t border-navy/10 py-3 text-[15px] leading-normal">
          {q}
        </li>
      ))}
    </ol>
  );
}
