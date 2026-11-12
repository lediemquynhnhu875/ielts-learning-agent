import { formatDateTime, formatDayTime } from "@/lib/format";

export type AttemptOption = { id: string; /** Điểm hoặc số câu đúng hiện đậm trên ô. */ value: string; savedAt: number };

type AttemptPickerProps = {
  attempts: AttemptOption[];
  activeId: string;
  /** Chữ đứng trước giá trị khi đọc bằng trình đọc màn hình, ví dụ "điểm", "đúng". */
  valueLabel: string;
  onSelect: (id: string) => void;
};

/** Chọn lượt làm: một thanh kính chia ô, mỗi ô là kết quả và thời điểm của lượt (mới nhất trước). */
export function AttemptPicker({ attempts, activeId, valueLabel, onSelect }: AttemptPickerProps) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span id="attempts-label" className="shrink-0 text-[13px] text-muted">
        Lượt làm
      </span>
      <div role="group" aria-labelledby="attempts-label" className="glass scroll-thin flex max-w-full gap-1 overflow-x-auto rounded-[20px] p-1">
        {attempts.map((a) => {
          const active = a.id === activeId;
          return (
            <button
              key={a.id}
              type="button"
              aria-pressed={active}
              aria-label={`Lượt ${formatDateTime(a.savedAt)}, ${valueLabel} ${a.value}`}
              onClick={() => onSelect(a.id)}
              className={`flex min-h-11 min-w-[84px] shrink-0 flex-col items-center justify-center rounded-[16px] px-3 py-1 leading-tight focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy ${
                active ? "bg-navy text-cream shadow-sm" : "hover:bg-white/60"
              }`}
            >
              <b className="text-[15px]">{a.value}</b>
              <span className={`text-[12px] ${active ? "text-cream/80" : "text-muted"}`}>{formatDayTime(a.savedAt)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
