import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";
import { WritingSession } from "@/features/writing/writing-session";
import { backendConfig } from "@/lib/backend/server-fetch";
import { writingExercises } from "@/mock-data/writing";

export function generateStaticParams() {
  return writingExercises.map((item) => ({ id: item.id }));
}

/** Màn làm bài Writing: bấm "Làm bài" ở thẻ Writing trong Kho đề vào thẳng đây (ui-rules #11). */
export default function Page({ params }: PageProps<"/writing/[id]">) {
  return (
    <Suspense fallback={<div aria-busy="true" aria-label="Đang tải đề" className="glass h-40 animate-pulse rounded-[32px] motion-reduce:animate-none" />}>
      <Writing params={params} />
    </Suspense>
  );
}

async function Writing({ params }: { params: PageProps<"/writing/[id]">["params"] }) {
  const { id } = await params;
  const exercise = writingExercises.find((item) => item.id === id && item.status === "verified");
  if (!exercise) notFound();
  // Đọc WRITING_MODE lúc có request (không đóng băng lúc build) để màn viết biết có cần rubric hay không.
  await connection();
  return <WritingSession exercise={exercise} mode={backendConfig().writingMode} />;
}
