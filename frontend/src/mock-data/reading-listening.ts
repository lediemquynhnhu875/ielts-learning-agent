/**
 * DỮ LIỆU GIẢ LẬP (mock) cho bài Reading/Listening, chưa lấy từ backend.
 * Hình dạng bám theo `GET /api/exercises/{id}` và trace UC-04 (docs/uc04.md).
 * Nội dung bài đọc là văn bản viết tạm cho giao diện, không phải đề thật.
 */
import type { ContentItemBase } from "./types";

export type QuestionKind =
  | "true_false_not_given"
  | "multiple_choice"
  | "sentence_completion"
  | "matching_headings";

export const questionKindLabel: Record<QuestionKind, string> = {
  true_false_not_given: "T/F/NG",
  multiple_choice: "MCQ",
  sentence_completion: "Fill",
  matching_headings: "Heading",
};

export type MockQuestion = {
  number: number;
  prompt: string;
  /** Đáp án và bằng chứng chỉ quản trị mới thấy. */
  answer: string;
  evidenceSpan: string | null;
};

export type MockQuestionGroup = {
  position: number;
  questionType: QuestionKind;
  instructions: string;
  questions: MockQuestion[];
};

/** Kết quả 5 chặng kiểm chứng UC-04, theo thứ tự trong agents/uc04/agent.py. */
export type Verification = {
  /** Chặng 1: chỉ nằm trong trace, không phải layer trong DB. */
  safetyPassed: boolean;
  /** Chặng 2: số lần sinh, tối đa 3. */
  attempts: number;
  /** Chặng 3: layer `rules`, chỉ có Đạt / không đạt. */
  rulesPassed: boolean;
  /** Chặng 4: layer `solver`, số câu giữ / số câu sinh. */
  solverRetained: number;
  solverGenerated: number;
  /** Chặng 5: layer `dedup`, cosine với các bài verified, ngưỡng 0.9. */
  maxSimilarity: number;
  nearestItemId: string | null;
  nearestItemTitle: string | null;
};

export const DEDUP_THRESHOLD = 0.9;

export type GenerationMetadata = {
  model: string;
  promptVersion: string;
  solverModel: string;
  solverPromptVersion: string;
  skillHash: string;
};

export type ReadingListeningExercise = ContentItemBase & {
  skill: "reading" | "listening";
  title: string;
  /** Reading: bài đọc. Listening: script. */
  text: string;
  /** Đoạn bằng chứng của câu đang mở trong trang chi tiết (mẫu). */
  highlightedSpan: string | null;
  questionKinds: QuestionKind[];
  questionGroups: MockQuestionGroup[];
  verification: Verification;
  metadata: GenerationMetadata;
};

const metadata: GenerationMetadata = {
  model: "gemini-flash",
  promptVersion: "reading-item-generation-v3",
  solverModel: "gpt-oss-120b",
  solverPromptVersion: "blind-solver-v2",
  skillHash: "9f2c41ab",
};

const cangioText = `[A] The Can Gio mangrove forest, south-east of Ho Chi Minh City, covers more than 70,000 hectares. After heavy damage during the war, replanting began in the late 1970s and the forest has since recovered enough to be recognised as a biosphere reserve.

[B] Mangroves protect the coast in several ways. Their roots slow incoming waves, which reduces erosion, and they trap sediment, which slowly builds new land at the river mouth.

[C] The forest is also a nursery for fish and crabs. Local families collect shellfish at low tide, and a small number of boat tours now bring visitors to see the monkeys that live along the canals.

[D] Managers face a difficult balance. More visitors bring income, but too many boats disturb nesting birds, so the number of daily trips is limited.`;

const metroText = `[A] Ho Chi Minh City's first metro line runs between Ben Thanh and Suoi Tien. The route was planned to ease traffic on one of the busiest corridors in the city.

[B] Construction took longer than first expected, partly because the underground section passes through the historic centre.

[C] Planners now hope that new bus routes feeding the stations will increase the number of daily passengers.`;

export const readingListeningExercises: ReadingListeningExercise[] = [
  {
    id: "rl-001",
    skill: "reading",
    title: "The Mangrove Forest of Can Gio",
    topic: "Mangrove forests",
    targetBand: 6.0,
    source: "llm_generated_verified",
    status: "verified",
    model: metadata.model,
    promptVersion: metadata.promptVersion,
    createdAt: "2026-10-26T09:12:00+07:00",
    reportCount: 2,
    text: cangioText,
    highlightedSpan: "Their roots slow incoming waves, which reduces erosion",
    questionKinds: ["true_false_not_given", "multiple_choice", "sentence_completion", "matching_headings"],
    questionGroups: [
      {
        position: 1,
        questionType: "true_false_not_given",
        instructions: "Do the following statements agree with the information given in the passage?",
        questions: [
          {
            number: 1,
            prompt: "The forest has been left untouched since the war.",
            answer: "FALSE",
            evidenceSpan: "replanting began in the late 1970s",
          },
          {
            number: 2,
            prompt: "Mangrove roots help reduce coastal erosion.",
            answer: "TRUE",
            evidenceSpan: "Their roots slow incoming waves, which reduces erosion",
          },
          {
            number: 3,
            prompt: "Visitors to the forest are charged a fee for each boat tour.",
            answer: "NOT GIVEN",
            evidenceSpan: null,
          },
        ],
      },
      {
        position: 2,
        questionType: "sentence_completion",
        instructions: "Complete the sentences. Write NO MORE THAN TWO WORDS for each answer.",
        questions: [
          {
            number: 4,
            prompt: "Mangroves trap ______ at the river mouth, which slowly builds new land.",
            answer: "sediment",
            evidenceSpan: "they trap sediment, which slowly builds new land",
          },
          {
            number: 5,
            prompt: "Too many boats disturb nesting ______.",
            answer: "birds",
            evidenceSpan: "too many boats disturb nesting birds",
          },
          {
            number: 6,
            prompt: "Local families collect ______ at low tide.",
            answer: "shellfish",
            evidenceSpan: "Local families collect shellfish at low tide",
          },
        ],
      },
      {
        position: 3,
        questionType: "multiple_choice",
        instructions: "Choose the correct letter, A, B, C or D.",
        questions: [
          {
            number: 7,
            prompt: "Why is the number of daily boat trips limited?",
            answer: "B",
            evidenceSpan: "too many boats disturb nesting birds, so the number of daily trips is limited",
          },
        ],
      },
      {
        position: 4,
        questionType: "matching_headings",
        instructions: "Choose the correct heading for each paragraph from the list of headings.",
        questions: [
          { number: 8, prompt: "Paragraph B", answer: "ii", evidenceSpan: "Mangroves protect the coast in several ways" },
          { number: 9, prompt: "Paragraph C", answer: "iv", evidenceSpan: "The forest is also a nursery for fish and crabs" },
          { number: 10, prompt: "Paragraph D", answer: "i", evidenceSpan: "Managers face a difficult balance" },
        ],
      },
    ],
    verification: {
      safetyPassed: true,
      attempts: 1,
      rulesPassed: true,
      solverRetained: 10,
      solverGenerated: 11,
      maxSimilarity: 0.42,
      nearestItemId: "rl-004",
      nearestItemTitle: "Hoi An: Preserving an Ancient Town",
    },
    metadata,
  },
  {
    id: "rl-002",
    skill: "reading",
    title: "Ho Chi Minh City's First Metro Line",
    topic: "Urban transport",
    targetBand: 6.5,
    source: "llm_generated_verified",
    status: "verified",
    model: metadata.model,
    promptVersion: metadata.promptVersion,
    createdAt: "2026-10-26T14:40:00+07:00",
    reportCount: 0,
    text: metroText,
    highlightedSpan: null,
    questionKinds: ["true_false_not_given", "multiple_choice", "matching_headings"],
    questionGroups: [],
    verification: {
      safetyPassed: true,
      attempts: 2,
      rulesPassed: true,
      solverRetained: 10,
      solverGenerated: 12,
      maxSimilarity: 0.61,
      nearestItemId: "rl-001",
      nearestItemTitle: "The Mangrove Forest of Can Gio",
    },
    metadata,
  },
  {
    id: "rl-003",
    skill: "listening",
    title: "A Morning at the Cai Rang Floating Market",
    topic: "Markets",
    targetBand: 5.5,
    source: "llm_generated_verified",
    status: "verified",
    model: metadata.model,
    promptVersion: metadata.promptVersion,
    createdAt: "2026-10-25T08:05:00+07:00",
    reportCount: 1,
    text: "Guide: Good morning, everyone. We leave the pier at five thirty, so please arrive a little early.",
    highlightedSpan: "We leave the pier at five thirty",
    questionKinds: ["sentence_completion", "multiple_choice", "true_false_not_given"],
    questionGroups: [],
    verification: {
      safetyPassed: true,
      attempts: 1,
      rulesPassed: true,
      solverRetained: 8,
      solverGenerated: 8,
      maxSimilarity: 0.3,
      nearestItemId: null,
      nearestItemTitle: null,
    },
    metadata: { ...metadata, promptVersion: "listening-item-generation-v2" },
  },
  {
    id: "rl-004",
    skill: "listening",
    title: "Hoi An: Preserving an Ancient Town",
    topic: "Heritage",
    targetBand: 6.5,
    source: "llm_generated_verified",
    status: "spare",
    model: metadata.model,
    promptVersion: metadata.promptVersion,
    createdAt: "2026-10-24T16:20:00+07:00",
    reportCount: 0,
    text: "Presenter: Today we look at how the old town of Hoi An balances tourism and preservation.",
    highlightedSpan: null,
    questionKinds: ["sentence_completion", "multiple_choice", "true_false_not_given"],
    questionGroups: [],
    verification: {
      safetyPassed: true,
      attempts: 3,
      rulesPassed: true,
      solverRetained: 9,
      solverGenerated: 11,
      maxSimilarity: 0.55,
      nearestItemId: "rl-001",
      nearestItemTitle: "The Mangrove Forest of Can Gio",
    },
    metadata: { ...metadata, promptVersion: "listening-item-generation-v2" },
  },
  {
    id: "rl-005",
    skill: "reading",
    title: "Saltwater Intrusion in the Mekong Delta",
    topic: "Climate",
    targetBand: 6.0,
    source: "llm_generated_verified",
    status: "rejected",
    model: metadata.model,
    promptVersion: metadata.promptVersion,
    createdAt: "2026-10-23T11:02:00+07:00",
    reportCount: 0,
    text: "[A] Every dry season, salt water moves further up the rivers of the Mekong Delta.",
    highlightedSpan: null,
    questionKinds: ["true_false_not_given", "sentence_completion", "multiple_choice"],
    questionGroups: [],
    verification: {
      safetyPassed: true,
      attempts: 1,
      rulesPassed: true,
      solverRetained: 10,
      solverGenerated: 10,
      maxSimilarity: 0.38,
      nearestItemId: null,
      nearestItemTitle: null,
    },
    metadata,
  },
];
