"use client";

import { useState } from "react";
import { createExercise } from "@/lib/api/client";
import { learnerCards } from "@/mock-data/exercises";
import { EmptyList, Rise } from "./admin-exercise-bank";
import { BackendExerciseList, useExerciseList } from "./backend-exercise-list";
import { BankHeader } from "./bank-header";
import { runCreateJob, type CreateRequest } from "./create-job";
import { CreateExerciseForm } from "./create-exercise-form";
import { ExerciseCard } from "./exercise-card";
import { GeneratingCard, type CreateJob } from "./generating-card";
import { SkillTabs } from "./skill-tabs";
import { useCardFilter } from "./use-card-filter";

// Writing và Speaking vẫn là dữ liệu mẫu: backend chưa có API liệt kê hai kỹ năng này.
const writingSpeakingCards = learnerCards("all").filter((card) => card.skill === "writing" || card.skill === "speaking");

/**
 * Trang Kho đề của người học (màn 11 trong mock).
 * Bài Reading/Listening lấy từ GET /api/exercises (chỉ bài đã kiểm chứng, lọc theo kỹ năng và ô tìm, phân trang);
 * bài Writing/Speaking là dữ liệu mẫu, lọc ở trình duyệt. "Tạo bài" gọi POST /api/exercises rồi lấy lại danh sách.
 */
export function LearnerExerciseBank({ canCreate }: { canCreate: boolean }) {
  const { skill, setSkill, query, setQuery, cards: sampleCards } = useCardFilter(writingSpeakingCards);
  const fromBackend = skill === "all" || skill === "reading" || skill === "listening";
  const list = useExerciseList({ skill: skill === "reading" || skill === "listening" ? skill : undefined, query, enabled: fromBackend });
  const [job, setJob] = useState<CreateJob | null>(null);

  async function create(request: CreateRequest) {
    const base = { id: `job-${Date.now()}`, request, startedAt: Date.now() };
    setJob({ ...base, state: "running" });
    const result = await runCreateJob(request, createExercise);
    if (result.ok) {
      setJob(null);
      list.reload();
    } else {
      setJob({ ...base, state: "failed", message: result.message, traceId: result.traceId });
    }
  }

  const showJob = canCreate && job && (skill === "all" || job.request.skill === skill);
  const nothing = sampleCards.length === 0 && (!fromBackend || (list.state.status === "ready" && list.state.cards.length === 0));

  return (
    <div className="flex flex-col gap-4">
      <BankHeader query={query} onQueryChange={setQuery} />
      <div
        className={`grid grid-cols-1 items-start gap-5 ${canCreate ? "min-[1150px]:grid-cols-[minmax(0,1fr)_280px]" : ""}`}
      >
        <div className="flex min-w-0 flex-col gap-4">
          <SkillTabs value={skill} onChange={setSkill} />
          <section key={skill} aria-label="Danh sách bài" className="flex flex-col gap-3.5">
            {showJob && (
              <GeneratingCard key={job.id} job={job} onRetry={() => create(job.request)} onDismiss={() => setJob(null)} />
            )}
            {fromBackend && <BackendExerciseList state={list.state} onLoadMore={list.loadMore} onRetry={list.reload} variant="learner" />}
            {sampleCards.map((card, i) => (
              <Rise key={card.id} index={i}>
                <ExerciseCard card={card} variant="learner" />
              </Rise>
            ))}
            {nothing && <EmptyList />}
          </section>
        </div>
        {canCreate && (
          <aside aria-label="Tạo bài mới">
            <CreateExerciseForm onCreate={create} busy={job?.state === "running"} />
          </aside>
        )}
      </div>
    </div>
  );
}
