import { formatDateTime } from "@/lib/format";
import type { ContentItemBase } from "@/mock-data/types";

type InfoItem = ContentItemBase & { license: string; author: string };

/** Cột thông tin của đề Writing/Speaking: các trường của CONTENT_ITEM, giữ nguyên giá trị gốc. */
export function InfoPanel({ item }: { item: InfoItem }) {
  const rows: [string, string][] = [
    ["Chủ đề", item.topic],
    ["Band mục tiêu", item.targetBand === null ? "–" : item.targetBand.toFixed(1)],
    ["Nguồn", item.source],
    ["Giấy phép", item.license],
    ["Tác giả", item.author],
    ["Tạo lúc", formatDateTime(item.createdAt)],
  ];
  return (
    <section aria-label="Thông tin" className="glass rounded-[26px] px-6 py-2">
      <dl>
        {rows.map(([label, value], i) => (
          <div
            key={label}
            className={`flex justify-between gap-4 py-3 text-sm ${i > 0 ? "border-t border-navy/10" : ""}`}
          >
            <dt className="text-muted">{label}</dt>
            <dd className="text-right font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
