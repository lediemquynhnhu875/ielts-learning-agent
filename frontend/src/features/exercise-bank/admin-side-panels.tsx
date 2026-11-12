import Link from "next/link";
import { FlagIcon } from "@/components/icons";
import type { QuestionReport } from "@/mock-data/reports";
import { statusLabel, type ExerciseStatus } from "@/mock-data/types";
import { StatusMark } from "./status-chip";

/** Thẻ navy "Câu bị báo sai": tên bài + số câu. */
export function ReportPanel({ reports }: { reports: QuestionReport[] }) {
  return (
    <section
      aria-labelledby="report-panel-title"
      className="rounded-[28px] border border-white/18 bg-linear-160 from-navy/94 to-navy-deep/96 px-6 pb-3.5 pt-6 text-cream shadow-[0_18px_44px_rgb(23_35_60/0.3)]"
    >
      <div className="flex items-center gap-2.5 text-base font-bold">
        <FlagIcon className="text-orange" strokeWidth={2.2} />
        <h2 id="report-panel-title">Câu bị báo sai</h2>
        <span className="ml-auto text-[30px] font-extrabold leading-none text-orange">{reports.length}</span>
      </div>
      <ul className="mt-3.5">
        {reports.map((r) => (
          <li key={r.id} className="border-t border-cream/14">
            <Link href={`/exercises/${r.exerciseId}`} className="flex items-center gap-3 py-3 hover:text-white">
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{r.exerciseTitle}</span>
              <span className="whitespace-nowrap rounded-full bg-orange/25 px-2.5 py-0.5 text-xs font-bold text-orange-light">
                Câu {r.questionNumber}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

const order: ExerciseStatus[] = ["verified", "spare", "rejected"];
const ringColor: Record<ExerciseStatus, string> = { verified: "#213d68", spare: "#eba45e", rejected: "#b5432f" };

/** Thẻ "Trạng thái kho": biểu đồ vòng + chú thích (màu + hình + chữ). */
export function BankStatusPanel({ counts }: { counts: Record<ExerciseStatus, number> }) {
  const total = order.reduce((sum, s) => sum + counts[s], 0);
  const r = 54;
  const circumference = 2 * Math.PI * r;
  const gap = 4;
  const segments = order.map((s, i) => {
    const length = total ? (counts[s] / total) * circumference : 0;
    const start = order.slice(0, i).reduce((sum, prev) => sum + (total ? (counts[prev] / total) * circumference : 0), 0);
    return { status: s, length, start };
  });

  return (
    <section aria-labelledby="status-panel-title" className="glass flex flex-col items-center gap-[18px] rounded-[28px] p-6">
      <h2 id="status-panel-title" className="self-start text-base font-bold">
        Trạng thái kho
      </h2>
      <svg
        width="124"
        height="124"
        viewBox="0 0 140 140"
        role="img"
        aria-label={order.map((s) => `${statusLabel[s]} ${counts[s]}`).join(", ")}
      >
        {segments
          .filter((seg) => seg.length > 0)
          .map((seg) => (
            <circle
              key={seg.status}
              cx="70"
              cy="70"
              r={r}
              fill="none"
              stroke={ringColor[seg.status]}
              strokeWidth="20"
              strokeDasharray={`${Math.max(seg.length - gap, 0)} ${circumference}`}
              strokeDashoffset={-seg.start}
              transform="rotate(-90 70 70)"
            />
          ))}
        <text x="70" y="78" textAnchor="middle" fontSize="32" fontWeight="800" fill="#17233c">
          {total}
        </text>
      </svg>
      <ul className="flex w-full flex-col gap-2.5">
        {order.map((s) => (
          <li key={s} className="flex items-center gap-2.5 text-sm">
            <StatusMark status={s} />
            <span className="flex-1">{statusLabel[s]}</span>
            <b>{counts[s]}</b>
          </li>
        ))}
      </ul>
    </section>
  );
}
