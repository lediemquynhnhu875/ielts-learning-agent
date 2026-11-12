"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronRightIcon, FlagIcon } from "@/components/icons";
import { readAttempts, type TestMode } from "@/features/reading-listening/attempt-store";
import { useSavedAttempts } from "@/features/writing/saved-result";
import { isUuid } from "@/lib/backend/proxy-rules";
import type { ExerciseCard as Card } from "@/mock-data/exercises";
import { skillLabel } from "@/mock-data/types";
import { skillVisual } from "./skill-visual";
import { StatusChip } from "./status-chip";

type ExerciseCardProps = {
  card: Card;
  /** Quản trị thấy chip trạng thái và số báo sai; người học thì không. `mock`: thẻ ở trang Thi thử. */
  variant: "admin" | "learner" | "mock";
};

const cardClass =
  "glass-card group grid min-h-[118px] grid-cols-[64px_minmax(0,1fr)] items-center gap-x-4 gap-y-3 rounded-[26px] py-3.5 pl-3.5 pr-5 sm:gap-5 sm:pr-6 sm:grid-cols-[88px_minmax(0,1fr)_auto]";
const cardHover = "transition-shadow hover:shadow-[0_0_0_2px_#eba45e,0_12px_30px_rgb(235_164_94/0.3)]";
const pill = "inline-flex items-center justify-center gap-2 rounded-full px-[18px] py-2.5 text-sm font-semibold";

/** Bài Reading/Listening đã có lượt nộp trên trình duyệt này chưa; đọc sau khi trang gắn vào trình duyệt. */
function useHasResult(mode: TestMode | null, exerciseId: string): boolean {
  const [has, setHas] = useState(false);
  useEffect(() => {
    if (!mode) return;
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) setHas(readAttempts(mode, exerciseId).some((a) => a.submitted));
    });
    return () => {
      cancelled = true;
    };
  }, [mode, exerciseId]);
  return has;
}

export function ExerciseCard({ card, variant }: ExerciseCardProps) {
  const admin = variant === "admin";
  const learnerWriting = !admin && card.skill === "writing";
  // Bài người học đã có kết quả (Writing đã chấm, Reading/Listening đã nộp): thẻ có hai nút "Xem kết quả" và "Làm lại".
  const attempts = useSavedAttempts(learnerWriting ? card.id : null);
  // Reading/Listening: lượt Luyện (Kho đề) và lượt Thi (Thi thử) lưu riêng; chỉ bài backend (id UUID) có lượt làm.
  const playable = !admin && isUuid(card.id) && (card.skill === "reading" || card.skill === "listening");
  const hasResult = useHasResult(playable ? (variant === "mock" ? "mock" : "practice") : null, card.id);

  if (hasResult || (learnerWriting && attempts && attempts.length > 0)) {
    const base = variant === "mock" ? `/mock/${card.id}` : learnerWriting ? `/writing/${card.id}` : `/exercises/${card.id}`;
    return (
      <div className={cardClass}>
        <CardBody card={card} admin={admin} />
        <div className="col-span-2 flex flex-wrap justify-end gap-2 sm:col-span-1 sm:flex-col sm:items-stretch">
          <Link href={`${base}?view=result`} className={`${pill} bg-navy text-cream`}>
            Xem kết quả
          </Link>
          <Link href={`${base}?redo=1`} className={`${pill} border border-navy/25 bg-white/70 hover:bg-white`}>
            Làm lại
          </Link>
        </div>
      </div>
    );
  }

  if (variant === "mock") {
    // Chỉ bài backend (id UUID) làm được; bài mẫu chưa có lượt làm ở backend.
    if (!isUuid(card.id)) {
      return (
        <div className={cardClass}>
          <CardBody card={card} admin={false} />
          <span className="col-span-2 justify-self-end text-sm font-semibold text-muted sm:col-span-1">Bài mẫu, chưa làm được</span>
        </div>
      );
    }
    return (
      <Link href={`/mock/${card.id}`} className={`${cardClass} ${cardHover}`}>
        <CardBody card={card} admin={false} />
        <span className={`${pill} col-span-2 justify-self-end bg-navy text-cream sm:col-span-1`}>
          Làm bài
          <ChevronRightIcon size={16} />
        </span>
      </Link>
    );
  }

  // Người học bấm "Làm bài" ở thẻ Writing thì vào thẳng màn viết (ui-rules #11).
  const href = learnerWriting ? `/writing/${card.id}` : `/exercises/${card.id}`;
  return (
    <Link href={href} className={`${cardClass} ${cardHover}`}>
      <CardBody card={card} admin={admin} />
      <span className={`${pill} col-span-2 justify-self-end bg-navy text-cream sm:col-span-1`}>
        {admin ? "Xem chi tiết" : "Làm bài"}
        <ChevronRightIcon size={16} />
      </span>
    </Link>
  );
}

function CardBody({ card, admin }: { card: Card; admin: boolean }) {
  const { icon: Icon, thumb } = skillVisual[card.skill];
  return (
    <>
      <span className={`relative grid size-16 place-items-center self-start overflow-hidden rounded-[18px] sm:size-[88px] sm:self-center sm:rounded-[20px] ${thumb}`}>
        <span aria-hidden="true" className="absolute -right-[22px] -top-[22px] size-[70px] rounded-full bg-white/16" />
        <Icon size={44} strokeWidth={1.7} className="size-7 sm:size-9" aria-label={skillLabel[card.skill]} />
      </span>

      <div className="min-w-0">
        <b className="block truncate text-base font-bold leading-[1.3] sm:text-[17px]" title={card.title}>
          {card.title}
        </b>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {admin && <StatusChip status={card.status} />}
          <MetaChip>{card.targetBand === null ? "Band –" : `Band ${card.targetBand.toFixed(1)}`}</MetaChip>
          {card.sizeLabel && <MetaChip>{card.sizeLabel}</MetaChip>}
          {admin && card.reportCount > 0 && (
            <MetaChip tone="danger" label={`${card.reportCount} câu bị báo sai`}>
              <FlagIcon size={13} />
              {card.reportCount}
            </MetaChip>
          )}
        </div>
        {card.detailLine && <div className="mt-2 text-[13px] text-muted">{card.detailLine}</div>}
      </div>
    </>
  );
}

function MetaChip({ children, tone, label }: { children: React.ReactNode; tone?: "danger"; label?: string }) {
  const color =
    tone === "danger"
      ? "border-status-rejected/25 bg-status-rejected/10 text-status-rejected-text"
      : "border-navy/12 bg-white/75 text-navy-deep";
  return (
    <span
      aria-label={label}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] text-xs font-semibold ${color}`}
    >
      {children}
    </span>
  );
}
