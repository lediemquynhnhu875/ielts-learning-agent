"use client";

import { useState } from "react";
import { EmptyList } from "./admin-exercise-bank";
import { BackendExerciseList, useExerciseList } from "./backend-exercise-list";
import { BankHeader } from "./bank-header";
import { SkillTabs, type SkillFilter } from "./skill-tabs";

/** Trang Thi thử của người học: bài Reading/Listening đã kiểm chứng từ GET /api/exercises, cùng nguồn và thẻ với Kho đề. */
export function MockTestBank() {
  const [skill, setSkill] = useState<SkillFilter>("all");
  const [query, setQuery] = useState("");
  const list = useExerciseList({ skill: skill === "reading" || skill === "listening" ? skill : undefined, query, enabled: true });

  return (
    <div className="flex flex-col gap-4">
      <BankHeader title="Thi thử" query={query} onQueryChange={setQuery} />
      <SkillTabs value={skill} onChange={setSkill} skills={["reading", "listening"]} />
      <section key={skill} aria-label="Danh sách bài" className="flex flex-col gap-3.5">
        <BackendExerciseList state={list.state} onLoadMore={list.loadMore} onRetry={list.reload} variant="mock" />
        {list.state.status === "ready" && list.state.cards.length === 0 && <EmptyList />}
      </section>
    </div>
  );
}
