import type { ReadingListeningExercise } from "@/mock-data/reading-listening";
import { DetailHeader } from "./detail-header";
import { PassageAndQuestions } from "./passage-and-questions";
import { MetadataChips, SimilarityPanel, VerificationPanel } from "./verification-panels";

/** Trang chi tiết bài Reading/Listening cho quản trị (màn 8 trong mock). */
export function ReadingListeningDetail({ exercise }: { exercise: ReadingListeningExercise }) {
  const questionCount = exercise.questionGroups.reduce((n, g) => n + g.questions.length, 0) || exercise.verification.solverRetained;

  return (
    <div className="flex flex-col gap-5">
      <DetailHeader
        skill={exercise.skill}
        title={exercise.title}
        status={exercise.status}
        meta={
          <>
            <b className="text-navy-deep">Band {exercise.targetBand?.toFixed(1) ?? "–"}</b>
            <span>{questionCount} câu</span>
          </>
        }
      />
      <div className="grid grid-cols-1 items-start gap-5 min-[1150px]:grid-cols-[minmax(0,1fr)_340px]">
        <PassageAndQuestions exercise={exercise} />
        <div className="flex flex-col gap-5">
          <VerificationPanel verification={exercise.verification} skill={exercise.skill} />
          <SimilarityPanel verification={exercise.verification} />
          <MetadataChips metadata={exercise.metadata} createdAt={exercise.createdAt} />
        </div>
      </div>
    </div>
  );
}
