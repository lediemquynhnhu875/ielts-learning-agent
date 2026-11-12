import type { ComponentType, SVGProps } from "react";
import { CheckIcon, ClockIcon, LinesIcon, LinkIcon, NotebookIcon, TargetIcon } from "@/components/icons";
import { writingTaskInfo, writingTitle, type WritingExercise } from "@/mock-data/writing";
import { DetailHeader } from "./detail-header";
import { InfoPanel } from "./info-panel";

type IconType = ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;

/** Icon theo thứ tự 4 tiêu chí UC-02: TA/TR, CC, LR, GRA. */
const criterionIcons: IconType[] = [TargetIcon, LinkIcon, NotebookIcon, CheckIcon];

/** Trang chi tiết đề Writing cho quản trị (màn 9 trong mock). */
export function WritingDetail({ exercise }: { exercise: WritingExercise }) {
  const task = writingTaskInfo[exercise.task];

  return (
    <div className="flex flex-col gap-5">
      <DetailHeader
        skill="writing"
        title={writingTitle(exercise)}
        status={exercise.status}
        meta={
          <>
            <b className="text-navy-deep">Band {exercise.targetBand?.toFixed(1) ?? "–"}</b>
            <span>{task.label}</span>
          </>
        }
      />
      <div className="grid grid-cols-1 items-start gap-5 min-[1150px]:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col gap-5">
          <section aria-label="Đề bài" className="glass rounded-[26px] bg-white/70 px-8 py-7">
            <div className="mb-4 flex flex-wrap gap-2">
              <TagChip>{task.label}</TagChip>
              {exercise.essayType && <TagChip>{exercise.essayType}</TagChip>}
            </div>
            <p className="max-w-[40ch] text-xl font-medium leading-relaxed">{exercise.prompt}</p>
          </section>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <StatTile icon={ClockIcon} label="Thời gian" value={`${task.minutes} phút`} />
            <StatTile icon={LinesIcon} label="Tối thiểu" value={`${task.minWords} từ`} />
          </div>

          <section aria-labelledby="criteria-title" className="glass rounded-[26px] bg-white/70 px-7 py-6">
            <h2 id="criteria-title" className="mb-4 text-base font-bold">
              Tiêu chí chấm
            </h2>
            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {task.criteria.map((name, i) => {
                const Icon = criterionIcons[i];
                return (
                  <li key={name} className="flex items-center gap-3 rounded-[18px] bg-skill-writing/14 px-4 py-3">
                    <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-skill-writing text-cream">
                      <Icon size={18} />
                    </span>
                    <b className="text-sm font-semibold">{name}</b>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
        <InfoPanel item={exercise} />
      </div>
    </div>
  );
}

function TagChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-skill-writing/18 px-3 py-1 text-xs font-semibold text-[#2c4f85]">{children}</span>
  );
}

function StatTile({ icon: Icon, label, value }: { icon: IconType; label: string; value: string }) {
  return (
    <div className="glass flex items-center gap-4 rounded-[26px] bg-white/70 px-6 py-5">
      <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-skill-writing text-cream">
        <Icon size={24} />
      </span>
      <div>
        <div className="text-[13px] text-muted">{label}</div>
        <b className="text-2xl font-extrabold">{value}</b>
      </div>
    </div>
  );
}
