import { useMemo, useState } from "react";
import type { ExerciseCard } from "@/mock-data/exercises";
import type { SkillFilter } from "./skill-tabs";

/** Lọc danh sách card theo tab kỹ năng và ô tìm (theo tên bài). */
export function useCardFilter(source: ExerciseCard[]) {
  const [skill, setSkill] = useState<SkillFilter>("all");
  const [query, setQuery] = useState("");

  const cards = useMemo(() => {
    const q = query.trim().toLowerCase();
    return source.filter(
      (card) => (skill === "all" || card.skill === skill) && (!q || card.title.toLowerCase().includes(q)),
    );
  }, [source, skill, query]);

  return { skill, setSkill, query, setQuery, cards };
}
