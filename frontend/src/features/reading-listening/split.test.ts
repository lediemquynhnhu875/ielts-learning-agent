import { describe, expect, it } from "vitest";
import { clampRatio, DEFAULT_RATIO, splitBounds } from "./split";

describe("clampRatio", () => {
  it("giữ tỉ lệ khi cả hai cột còn rộng từ 360px", () => {
    expect(clampRatio(0.5, 1068)).toBe(0.5);
  });

  it("kẹp để không cột nào hẹp hơn 360px (đã trừ 68px của thanh chia, đệm và thanh cuộn)", () => {
    expect(clampRatio(0.1, 1068)).toBeCloseTo(0.36);
    expect(clampRatio(0.95, 1068)).toBeCloseTo(0.64);
    expect(splitBounds(1068)).toEqual([0.36, 0.64]);
  });

  it("vùng chứa quá hẹp cho hai cột 360px thì chia đôi", () => {
    expect(clampRatio(0.8, 780)).toBe(0.5);
    expect(splitBounds(780)).toEqual([0.5, 0.5]);
  });

  it("giá trị hỏng (NaN, không phải số) về mặc định", () => {
    expect(clampRatio(Number.NaN, 1048)).toBe(DEFAULT_RATIO);
    expect(clampRatio(Number("abc"), 1048)).toBe(DEFAULT_RATIO);
  });

  it("chưa đo được bề rộng thì chỉ kẹp trong 0–1", () => {
    expect(clampRatio(0.7, 0)).toBe(0.7);
    expect(clampRatio(3, 0)).toBe(1);
  });
});
