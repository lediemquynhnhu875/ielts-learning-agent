import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";
import { SampleOnly } from "@/components/learner-only";
import { PagePlaceholder } from "@/components/page-placeholder";
import { DetailError, DetailSkeleton } from "@/features/exercise-detail/detail-states";
import { loadReadingListeningDetail } from "@/features/exercise-detail/from-api";
import { ReadingListeningDetail } from "@/features/exercise-detail/reading-listening-detail";
import { SpeakingDetail } from "@/features/exercise-detail/speaking-detail";
import { WritingDetail } from "@/features/exercise-detail/writing-detail";
import { loadPlayable } from "@/features/reading-listening/load-playable";
import { TestSession } from "@/features/reading-listening/test-session";
import { ApiError } from "@/lib/api/errors";
import { isUuid } from "@/lib/backend/proxy-rules";
import { createServerFetch } from "@/lib/backend/server-fetch";
import { readingListeningExercises } from "@/mock-data/reading-listening";
import { mockSession } from "@/mock-data/session";
import { speakingExercises } from "@/mock-data/speaking";
import { writingExercises } from "@/mock-data/writing";

export function generateStaticParams() {
  return [...readingListeningExercises, ...writingExercises, ...speakingExercises].map((item) => ({ id: item.id }));
}

type Params = PageProps<"/exercises/[id]">["params"];

export default function Page({ params }: PageProps<"/exercises/[id]">) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <Detail params={params} />
    </Suspense>
  );
}

// Trang chi tiết có đáp án, bằng chứng, kết quả kiểm chứng: chỉ dành cho quản trị.
// Người học mở bài backend (UUID) thì vào màn làm bài chế độ Luyện.
const isTeacher = mockSession?.role === "teacher";

async function Detail({ params }: { params: Params }) {
  const { id } = await params;
  // Bài từ backend có id UUID; Writing/Speaking và bài mẫu cũ vẫn đọc mock (backend chưa có endpoint).
  if (isUuid(id)) return isTeacher ? <ApiDetail id={id} /> : <LearnerPractice id={id} />;

  const readingListening = readingListeningExercises.find((item) => item.id === id);
  const writing = writingExercises.find((item) => item.id === id);
  const speaking = speakingExercises.find((item) => item.id === id);
  if (!readingListening && !writing && !speaking) notFound();
  if (!isTeacher && writing) redirect(`/writing/${writing.id}`);
  if (!isTeacher && readingListening) return <SampleOnly title={readingListening.title} />;
  if (!isTeacher) return <PagePlaceholder title="Làm bài" />;

  if (readingListening) return <ReadingListeningDetail exercise={readingListening} />;
  if (writing) return <WritingDetail exercise={writing} />;
  return <SpeakingDetail exercise={speaking!} />;
}

const errorMessage = (error: unknown) => (error instanceof ApiError ? error.message : "Lỗi không xác định.");

/** Quản trị: đọc bài, đáp án và trace thật (gọi thẳng backend phía server, token không ra trình duyệt). */
async function ApiDetail({ id }: { id: string }) {
  let detail;
  try {
    detail = await loadReadingListeningDetail(id, createServerFetch());
  } catch (error) {
    return <DetailError message={errorMessage(error)} />;
  }
  if (!detail) notFound();
  return <ReadingListeningDetail exercise={detail} />;
}

/** Người học: màn làm bài chế độ Luyện; trang server chỉ đọc skill, title, status (không gọi đáp án hay trace). */
async function LearnerPractice({ id }: { id: string }) {
  const playable = await loadPlayable(id);
  if ("error" in playable) return <DetailError message={playable.error} />;
  return <TestSession exercise={playable} mode="practice" />;
}
