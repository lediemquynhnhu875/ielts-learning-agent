import { Suspense } from "react";
import { LearnerOnly } from "@/components/learner-only";
import { DetailError, DetailSkeleton } from "@/features/exercise-detail/detail-states";
import { loadPlayable } from "@/features/reading-listening/load-playable";
import { TestSession } from "@/features/reading-listening/test-session";
import { mockSession } from "@/mock-data/session";

/** Màn làm bài chế độ Thi, chỉ cho người học. Id là runtime data (không có generateStaticParams) nên đọc trong Suspense. */
export default function Page({ params }: PageProps<"/mock/[id]">) {
  if (mockSession?.role !== "learner") return <LearnerOnly />;
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <MockTest params={params} />
    </Suspense>
  );
}

async function MockTest({ params }: { params: PageProps<"/mock/[id]">["params"] }) {
  const { id } = await params;
  const playable = await loadPlayable(id);
  if ("error" in playable) return <DetailError message={playable.error} />;
  return <TestSession exercise={playable} mode="mock" />;
}
