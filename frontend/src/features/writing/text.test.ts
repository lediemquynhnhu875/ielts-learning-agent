import { describe, expect, it } from "vitest";
import { countWords, formatClock, formatDuration, remainingSeconds, wordRatio } from "./text";

describe("countWords", () => {
  it("đếm từ đúng regex của backend Writing", () => {
    expect(countWords("")).toBe(0);
    expect(countWords("   \n  ")).toBe(0);
    expect(countWords("Many cities like Ho Chi Minh City")).toBe(7);
  });

  it("từ có dấu nháy hoặc gạch nối tính là một từ", () => {
    expect(countWords("It's a well-known fact")).toBe(4);
    expect(countWords("children’s long-term health")).toBe(3);
  });

  it("số tính là từ, dấu câu đứng riêng không tính", () => {
    expect(countWords("In 2021, 34,000 people came — wow!")).toBe(7); // "34,000" tách ở dấu phẩy như backend
    expect(countWords("- , . !")).toBe(0);
  });

  it("chữ có dấu (không thuộc A-Z) không được tính như backend", () => {
    expect(countWords("café")).toBe(1);
    expect(countWords("Việt Nam")).toBe(3);
  });
});

describe("wordRatio", () => {
  it("tỉ lệ thanh tiến độ theo số từ tối thiểu", () => {
    expect(wordRatio(130, 250)).toBe(0.52);
  });

  it("không vượt 1 khi đã đủ", () => {
    expect(wordRatio(300, 250)).toBe(1);
  });
});

describe("remainingSeconds", () => {
  const start = Date.UTC(2026, 9, 31, 7, 0, 0);

  it("tính thời gian còn lại từ lúc bắt đầu", () => {
    expect(remainingSeconds(start, start, 40)).toBe(2400);
    expect(remainingSeconds(start, start + 61_500, 40)).toBe(2339);
  });

  it("không âm khi đã hết giờ", () => {
    expect(remainingSeconds(start, start + 50 * 60_000, 40)).toBe(0);
  });
});

describe("formatClock", () => {
  it("định dạng mm:ss", () => {
    expect(formatClock(2400)).toBe("40:00");
    expect(formatClock(1934)).toBe("32:14");
    expect(formatClock(5)).toBe("00:05");
    expect(formatClock(0)).toBe("00:00");
  });
});

describe("formatDuration", () => {
  it("thời gian làm bài theo phút, làm tròn lên", () => {
    expect(formatDuration(23 * 60 + 10)).toBe("Làm trong 24 phút");
    expect(formatDuration(40 * 60)).toBe("Làm trong 40 phút");
  });

  it("dưới một phút ghi rõ", () => {
    expect(formatDuration(35)).toBe("Làm trong dưới 1 phút");
  });

  it("từ một giờ trở lên ghi giờ và phút", () => {
    expect(formatDuration(75 * 60)).toBe("Làm trong 1 giờ 15 phút");
  });
});
