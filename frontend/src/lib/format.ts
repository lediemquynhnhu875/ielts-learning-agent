const parts = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ho_Chi_Minh",
  hour: "2-digit",
  minute: "2-digit",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hourCycle: "h23",
});

const fields = (value: string | number) => Object.fromEntries(parts.formatToParts(new Date(value)).map((x) => [x.type, x.value]));

/** Ngày giờ theo quy ước giao diện: giờ trước, ngày sau, có năm — `HH:mm dd/MM/yyyy`. Nhận chuỗi ISO hoặc mốc ms. */
export function formatDateTime(value: string | number): string {
  const p = fields(value);
  return `${p.hour}:${p.minute} ${p.day}/${p.month}/${p.year}`;
}

/** Chỉ giờ phút `HH:mm`, giờ Việt Nam. */
export function formatTime(value: string | number): string {
  const p = fields(value);
  return `${p.hour}:${p.minute}`;
}

/** Giờ phút kèm ngày tháng, không có năm — `HH:mm dd/MM`; cho chỗ hẹp như thanh chọn lượt làm. */
export function formatDayTime(value: string | number): string {
  const p = fields(value);
  return `${p.hour}:${p.minute} ${p.day}/${p.month}`;
}
