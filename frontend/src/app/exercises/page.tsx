import { AdminExerciseBank } from "@/features/exercise-bank/admin-exercise-bank";
import { LearnerExerciseBank } from "@/features/exercise-bank/learner-exercise-bank";
import { mockSession } from "@/mock-data/session";

export default function Page() {
  // Vai trò lấy theo tài khoản. Chưa đăng nhập: xem như người học nhưng không tạo bài.
  if (mockSession?.role === "teacher") return <AdminExerciseBank />;
  return <LearnerExerciseBank canCreate={mockSession !== null} />;
}
