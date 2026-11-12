/**
 * DỮ LIỆU GIẢ LẬP (mock): gộp 4 kỹ năng thành một danh sách card cho trang Kho đề.
 * Khi backend có API liệt kê kho, thay file này bằng API client.
 * 1 card = 1 content item: Reading = một bài đọc, Listening = một part,
 * Writing = một đề, Speaking = một bộ Part 1–3.
 */
import { questionKindLabel, readingListeningExercises } from "./reading-listening";
import { speakingExercises } from "./speaking";
import type { ExerciseStatus, Skill } from "./types";
import { writingExercises, writingTaskInfo, writingTitle } from "./writing";

export type ExerciseCard = {
  id: string;
  skill: Skill;
  /** Tên hiển thị: giữ nguyên bản gốc, không dịch. Writing ghép từ topic (ui-rules #8); Speaking chưa có cột tiêu đề. */
  title: string;
  status: ExerciseStatus;
  targetBand: number | null;
  /** Chip phụ: "10 câu", "Task 2", "Part 1–3". */
  sizeLabel: string;
  /** Dòng dưới tên: dạng câu hỏi hoặc dạng đề. */
  detailLine: string;
  reportCount: number;
  createdAt: string;
};

const readingListeningCards: ExerciseCard[] = readingListeningExercises.map((item) => ({
  id: item.id,
  skill: item.skill,
  title: item.title,
  status: item.status,
  targetBand: item.targetBand,
  sizeLabel: `${item.verification.solverRetained} câu`,
  detailLine: item.questionKinds.map((kind) => questionKindLabel[kind]).join(" · "),
  reportCount: item.reportCount,
  createdAt: item.createdAt,
}));

const writingCards: ExerciseCard[] = writingExercises.map((item) => ({
  id: item.id,
  skill: item.skill,
  title: writingTitle(item),
  status: item.status,
  targetBand: item.targetBand,
  sizeLabel: writingTaskInfo[item.task].label,
  detailLine: item.essayType ?? "",
  reportCount: item.reportCount,
  createdAt: item.createdAt,
}));

const speakingCards: ExerciseCard[] = speakingExercises.map((item) => ({
  id: item.id,
  skill: item.skill,
  title: item.part2.cue,
  status: item.status,
  targetBand: item.targetBand,
  sizeLabel: "Part 1–3",
  detailLine: item.topic,
  reportCount: item.reportCount,
  createdAt: item.createdAt,
}));

/** Mới nhất trước. */
export const exerciseCards: ExerciseCard[] = [...readingListeningCards, ...writingCards, ...speakingCards].sort(
  (a, b) => b.createdAt.localeCompare(a.createdAt),
);

export function cardsBySkill(skill: Skill | "all"): ExerciseCard[] {
  return skill === "all" ? exerciseCards : exerciseCards.filter((card) => card.skill === skill);
}

/** Số bài theo trạng thái, cho thẻ "Trạng thái kho" của quản trị. */
export function statusCounts(): Record<ExerciseStatus, number> {
  const counts: Record<ExerciseStatus, number> = { verified: 0, spare: 0, rejected: 0 };
  for (const card of exerciseCards) counts[card.status] += 1;
  return counts;
}

/** Chỉ bài `verified` được phát cho người học. */
export function learnerCards(skill: Skill | "all"): ExerciseCard[] {
  return cardsBySkill(skill).filter((card) => card.status === "verified");
}
