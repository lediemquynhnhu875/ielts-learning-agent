import { describe, expect, it } from "vitest";
import { formatDateTime, formatDayTime, formatTime } from "./format";

// 31/10/2026 11:05 UTC = 18:05 giờ Việt Nam.
const ms = Date.UTC(2026, 9, 31, 11, 5);

describe("formatDateTime", () => {
  it("nhận chuỗi ISO hoặc mốc ms, hiện giờ Việt Nam dạng HH:mm dd/MM/yyyy", () => {
    expect(formatDateTime(new Date(ms).toISOString())).toBe("18:05 31/10/2026");
    expect(formatDateTime(ms)).toBe("18:05 31/10/2026");
  });
});

describe("formatTime", () => {
  it("chỉ giờ phút, giờ Việt Nam", () => {
    expect(formatTime(ms)).toBe("18:05");
  });
});

describe("formatDayTime", () => {
  it("giờ phút kèm ngày tháng, không có năm", () => {
    expect(formatDayTime(ms)).toBe("18:05 31/10");
  });
});
