import Link from "next/link";
import type { ReactNode } from "react";
import { ChevronLeftIcon } from "@/components/icons";
import { StatusChip } from "@/features/exercise-bank/status-chip";
import { skillVisual } from "@/features/exercise-bank/skill-visual";
import type { ExerciseStatus, Skill } from "@/mock-data/types";

type DetailHeaderProps = {
  skill: Skill;
  title: string;
  status: ExerciseStatus;
  /** Band, số câu / Task / Part: hiển thị sau chip trạng thái. */
  meta: ReactNode;
};

/**
 * Header trang chi tiết (quản trị): quay lại, ô kỹ năng, tên bài, trạng thái.
 * Không có nút đổi trạng thái: tài liệu không mô tả (ui-rules #4).
 */
export function DetailHeader({ skill, title, status, meta }: DetailHeaderProps) {
  const { icon: Icon, tile } = skillVisual[skill];

  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-3">
      <Link
        href="/exercises"
        aria-label="Quay lại Kho đề"
        className="glass grid size-10 shrink-0 place-items-center rounded-full hover:bg-white/70"
      >
        <ChevronLeftIcon size={19} />
      </Link>
      <span className={`grid size-12 shrink-0 place-items-center rounded-2xl ${tile}`}>
        <Icon size={24} />
      </span>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[26px] font-extrabold leading-tight tracking-[-0.015em]" title={title}>
          {title}
        </h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-3 text-sm text-muted">
          <StatusChip status={status} />
          {meta}
        </div>
      </div>
    </header>
  );
}
