import { LearnerOnly } from "@/components/learner-only";
import { MockTestBank } from "@/features/exercise-bank/mock-test-bank";
import { mockSession } from "@/mock-data/session";

/** Thi thử: danh sách bài Reading/Listening, chỉ cho người học (giáo viên và người chưa đăng nhập thấy LearnerOnly). */
export default function Page() {
  if (mockSession?.role !== "learner") return <LearnerOnly />;
  return <MockTestBank />;
}
