"use client";

import { exerciseCards, statusCounts } from "@/mock-data/exercises";
import { mockReports } from "@/mock-data/reports";
import { BankHeader } from "./bank-header";
import { BankStatusPanel, ReportPanel } from "./admin-side-panels";
import { ExerciseCard } from "./exercise-card";
import { SkillTabs } from "./skill-tabs";
import { useCardFilter } from "./use-card-filter";

/** Trang Kho đề của quản trị (màn 6 trong mock). */
export function AdminExerciseBank() {
  const { skill, setSkill, query, setQuery, cards } = useCardFilter(exerciseCards);

  return (
    <div className="flex flex-col gap-4">
      <BankHeader query={query} onQueryChange={setQuery} />
      <div className="grid grid-cols-1 items-start gap-5 min-[1150px]:grid-cols-[minmax(0,1fr)_280px]">
        <div className="flex min-w-0 flex-col gap-4">
          <SkillTabs value={skill} onChange={setSkill} />
          <section key={skill} aria-label="Danh sách bài" className="flex flex-col gap-3.5">
            {cards.length > 0 ? (
              cards.map((card, i) => (
                <Rise key={card.id} index={i}>
                  <ExerciseCard card={card} variant="admin" />
                </Rise>
              ))
            ) : (
              <EmptyList />
            )}
          </section>
        </div>
        <aside className="flex flex-col gap-5" aria-label="Tổng quan kho">
          <ReportPanel reports={mockReports} />
          <BankStatusPanel counts={statusCounts()} />
        </aside>
      </div>
    </div>
  );
}

/** Hiện dần từng card khi đổi tab (lệch nhau một chút cho mượt). */
export function Rise({ index, children }: { index: number; children: React.ReactNode }) {
  return (
    <div className="animate-rise-in" style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}>
      {children}
    </div>
  );
}

export function EmptyList() {
  return <p className="glass rounded-[26px] px-6 py-10 text-center text-muted">Không có bài phù hợp</p>;
}
