/**
 * DỮ LIỆU GIẢ LẬP (mock): câu bị người học báo sai, đang chờ xử lý.
 * Bảng `QUESTION_REPORT (id, question_id, status)` có trong ERD nhưng backend chưa có endpoint.
 */

export type QuestionReport = {
  id: string;
  exerciseId: string;
  exerciseTitle: string;
  questionNumber: number;
};

export const mockReports: QuestionReport[] = [
  { id: "rp-001", exerciseId: "rl-001", exerciseTitle: "The Mangrove Forest of Can Gio", questionNumber: 3 },
  { id: "rp-002", exerciseId: "rl-001", exerciseTitle: "The Mangrove Forest of Can Gio", questionNumber: 5 },
  { id: "rp-003", exerciseId: "rl-003", exerciseTitle: "A Morning at the Cai Rang Floating Market", questionNumber: 2 },
];
