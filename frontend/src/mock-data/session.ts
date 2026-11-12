/**
 * DỮ LIỆU GIẢ LẬP (mock), chưa lấy từ backend.
 * Backend chưa có đăng nhập; khi có API thì thay file này bằng phiên đăng nhập thật.
 * Đổi `mockSession` sang `mockLearner` hoặc `null` để xem các trạng thái khác của thanh bên.
 */

import { mockReports } from "./reports";

export type Role = "teacher" | "learner";

export type SessionUser = {
  name: string;
  role: Role;
};

export const roleLabel: Record<Role, string> = {
  teacher: "Giáo viên",
  learner: "Người học",
};

export const mockTeacher: SessionUser = { name: "Trần Thu Hà", role: "teacher" };
export const mockLearner: SessionUser = { name: "Nguyễn Minh Anh", role: "learner" };

/** Người dùng đang đăng nhập; `null` là chưa đăng nhập. */
export const mockSession: SessionUser | null = mockTeacher; // đổi sang mockLearner hoặc null để xem các trạng thái khác của thanh bên

/** Số câu bị báo sai đang chờ xử lý (badge ở thanh bên). */
export const mockReportCount = mockReports.length;
