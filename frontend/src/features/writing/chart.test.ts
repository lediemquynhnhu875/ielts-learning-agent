import { describe, expect, it } from "vitest";
import { chartScale } from "./chart";

describe("chartScale", () => {
  it("chọn bước chia tròn và đỉnh trục phủ giá trị lớn nhất", () => {
    expect(chartScale([34, 21, 12, 58, 36, 35])).toEqual({ max: 60, ticks: [0, 20, 40, 60] });
  });

  it("giá trị nhỏ dùng bước nhỏ", () => {
    expect(chartScale([1.2, 3.4, 2])).toEqual({ max: 4, ticks: [0, 1, 2, 3, 4] });
  });

  it("giá trị lớn dùng bước lớn", () => {
    expect(chartScale([120, 480, 950])).toEqual({ max: 1000, ticks: [0, 200, 400, 600, 800, 1000] });
  });

  it("không có số dương thì vẫn có trục 0 đến 1", () => {
    expect(chartScale([])).toEqual({ max: 1, ticks: [0, 1] });
    expect(chartScale([0, 0])).toEqual({ max: 1, ticks: [0, 1] });
  });
});
