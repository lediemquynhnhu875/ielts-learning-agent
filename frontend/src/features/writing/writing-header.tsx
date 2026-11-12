import Link from "next/link";
import type { ReactNode } from "react";
import { ChevronLeftIcon, ClockIcon } from "@/components/icons";
import { skillVisual } from "@/features/exercise-bank/skill-visual";
import type { Skill } from "@/mock-data/types";

type WritingHeaderProps = {
  title: string;
  /** Các mục nhỏ dưới tiêu đề (dạng đề, thời gian, số từ), mỗi mục một span. */
  meta: string[];
  /** Đồng hồ hoặc ô điểm, nằm bên phải. */
  aside?: ReactNode;
  /** Ô kỹ năng; mặc định Writing. */
  skill?: Skill;
  /** Nút quay lại; mặc định về Kho đề. */
  back?: { href: string; label: string };
};

/** Header trang làm bài và kết quả, theo header trang giáo viên: nút tròn quay lại, ô kỹ năng, tiêu đề, dòng phụ. */
export function WritingHeader({ title, meta, aside, skill = "writing", back = { href: "/exercises", label: "Quay lại Kho đề" } }: WritingHeaderProps) {
  const { icon: Icon, tile } = skillVisual[skill];
  return (
    <header className="flex flex-wrap items-center gap-x-[18px] gap-y-3 py-1">
      <Link
        href={back.href}
        aria-label={back.label}
        className="glass grid size-11 shrink-0 place-items-center rounded-full hover:bg-white/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
      >
        <ChevronLeftIcon size={20} />
      </Link>
      <span aria-hidden="true" className={`grid size-[52px] shrink-0 place-items-center rounded-[18px] ${tile}`}>
        <Icon size={26} />
      </span>
      <div className="min-w-0 flex-1 basis-[200px]">
        <h1 className="text-[26px] lg:truncate font-extrabold leading-tight tracking-[-0.015em] md:text-[30px]" title={title}>
          {title}
        </h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3.5 gap-y-1 text-[15px] text-muted">
          {meta.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </div>
      {aside && <div className="ml-auto shrink-0">{aside}</div>}
    </header>
  );
}

/** Đồng hồ: viên kính nhỏ chỉ có biểu tượng và số. */
export function WritingClock({ label, ended = false }: { label: string; ended?: boolean }) {
  return (
    <div
      role="timer"
      aria-label={ended ? "Hết giờ" : `Thời gian còn lại ${label}`}
      className={`glass inline-flex items-center gap-2 rounded-full py-2 pl-3.5 pr-[18px] ${
        ended ? "bg-[#fdece8]/90 text-status-rejected-text" : "bg-white/50"
      }`}
    >
      <ClockIcon size={18} className={ended ? "text-status-rejected" : "text-skill-speaking"} />
      <b className="text-2xl font-extrabold tracking-[0.01em]">{label}</b>
    </div>
  );
}

/** Ô điểm tổng ở trang kết quả: chỉ nhãn "Điểm ước lượng" và số; chưa có điểm thì "—". */
export function ScoreMedal({ value, note }: { value: string; note?: string }) {
  return (
    <div
      role="group"
      aria-label={`Điểm ước lượng ${value}${note ? `, ${note}` : ""}`}
      className="glass flex flex-col items-end rounded-3xl bg-white/50 px-[26px] py-3"
    >
      <small className="text-[13px] font-semibold text-muted">Điểm ước lượng</small>
      <b className="text-[52px] font-extrabold leading-none tracking-[-0.02em] text-navy">{value}</b>
      {note && <em className="text-[13px] font-bold not-italic text-status-spare-text">{note}</em>}
    </div>
  );
}
