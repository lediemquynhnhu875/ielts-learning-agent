import { statusLabel, type ExerciseStatus } from "@/mock-data/types";

/** Trạng thái hiển thị bằng màu + hình + chữ: tròn (Xác nhận), vuông (Dự phòng), tam giác (Đã loại). */
const style: Record<ExerciseStatus, { chip: string; mark: string }> = {
  verified: { chip: "bg-navy/13 text-navy", mark: "rounded-full" },
  spare: { chip: "bg-orange/34 text-status-spare-text", mark: "rounded-[2px]" },
  rejected: {
    chip: "bg-status-rejected/15 text-status-rejected-text",
    mark: "[clip-path:polygon(50%_0,100%_100%,0_100%)]",
  },
};

export function StatusChip({ status }: { status: ExerciseStatus }) {
  const s = style[status];
  return (
    <span className={`inline-flex items-center gap-[7px] whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${s.chip}`}>
      <i aria-hidden="true" className={`block size-2 bg-current ${s.mark}`} />
      {statusLabel[status]}
    </span>
  );
}

/** Dấu hình nhỏ cho chú thích (legend). */
export function StatusMark({ status, className = "" }: { status: ExerciseStatus; className?: string }) {
  const color = { verified: "bg-status-verified", spare: "bg-status-spare", rejected: "bg-status-rejected" }[status];
  return <i aria-hidden="true" className={`block size-2.5 ${color} ${style[status].mark} ${className}`} />;
}
