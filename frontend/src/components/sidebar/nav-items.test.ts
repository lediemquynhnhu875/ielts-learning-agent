import { describe, expect, it } from "vitest";
import { mockLearner, mockTeacher } from "@/mock-data/session";
import { visibleNavItems } from "./nav-items";

const hrefs = (user: Parameters<typeof visibleNavItems>[0]) => visibleNavItems(user).map((item) => item.href);

describe("visibleNavItems", () => {
  it("người học thấy Thi thử ngay sau Kho đề, không thấy Câu bị báo sai", () => {
    const list = hrefs(mockLearner);
    expect(list.indexOf("/mock")).toBe(list.indexOf("/exercises") + 1);
    expect(list).not.toContain("/reports");
    expect(visibleNavItems(mockLearner).find((item) => item.href === "/mock")?.label).toBe("Thi thử");
  });

  it("giáo viên không thấy Thi thử, vẫn thấy Câu bị báo sai", () => {
    expect(hrefs(mockTeacher)).not.toContain("/mock");
    expect(hrefs(mockTeacher)).toContain("/reports");
  });

  it("chưa đăng nhập chỉ thấy các mục không giới hạn vai trò", () => {
    expect(hrefs(null)).toEqual(["/", "/exercises", "/stats", "/settings"]);
  });
});
