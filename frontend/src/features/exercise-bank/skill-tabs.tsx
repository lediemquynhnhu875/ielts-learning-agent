import { skillLabel, type Skill } from "@/mock-data/types";
import { skillVisual } from "./skill-visual";

export type SkillFilter = Skill | "all";

const allSkills: Skill[] = ["reading", "listening", "writing", "speaking"];

type SkillTabsProps = {
  value: SkillFilter;
  onChange: (value: SkillFilter) => void;
  /** Kỹ năng có tab; mặc định cả 4. */
  skills?: Skill[];
};

/** Thanh chọn kỹ năng dạng viên thuốc: Tất cả, Reading, Listening, Writing, Speaking. */
export function SkillTabs({ value, onChange, skills = allSkills }: SkillTabsProps) {
  const options: { key: SkillFilter; label: string }[] = [
    { key: "all", label: "Tất cả" },
    ...skills.map((s) => ({ key: s, label: skillLabel[s] })),
  ];

  return (
    <div className="scroll-thin w-full overflow-x-auto">
      <div role="group" aria-label="Lọc theo kỹ năng" className="flex min-w-max gap-[3px] rounded-full bg-navy/10 p-1 sm:min-w-0">
        {options.map(({ key, label }) => {
          const on = value === key;
          const Icon = key === "all" ? null : skillVisual[key].icon;
          return (
            <button
              key={key}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(key)}
              className={`flex flex-1 shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full px-[18px] py-2 text-sm transition-[color,background-color,box-shadow] duration-200 ease-out ${
                on
                  ? "bg-cream font-semibold text-navy-deep shadow-[0_2px_8px_rgb(33_61_104/0.15)]"
                  : "font-medium text-muted hover:text-navy-deep"
              }`}
            >
              {Icon && <Icon size={15} />}
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
