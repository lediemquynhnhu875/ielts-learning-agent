/**
 * DỮ LIỆU GIẢ LẬP (mock) cho đề Writing, chưa lấy từ backend (backend chưa có API đề).
 * Thời gian, số từ tối thiểu và tiêu chí chấm theo UC-02 trong đề tài.
 * Đề Task 2 lấy từ ví dụ trong đề tài; đề Task 1 và số liệu biểu đồ viết tạm cho giao diện.
 * Kết quả mẫu Task 1 (`sampleTask1Result`) dùng cho màn kết quả Task 1 cho tới khi backend chấm được Task 1.
 */
import type { WritingAssessment } from "@/lib/api/writing";
import type { ContentItemBase } from "./types";

export type WritingTask = "task1" | "task2";

export type WritingTaskInfo = {
  label: string;
  minutes: number;
  minWords: number;
  /** Tiêu chí đầu khác nhau giữa hai task; ba tiêu chí còn lại dùng chung. */
  criteria: [string, string, string, string];
};

const sharedCriteria = ["Coherence and Cohesion", "Lexical Resource", "Grammatical Range and Accuracy"] as const;

export const writingTaskInfo: Record<WritingTask, WritingTaskInfo> = {
  task1: { label: "Task 1", minutes: 20, minWords: 150, criteria: ["Task Achievement", ...sharedCriteria] },
  task2: { label: "Task 2", minutes: 40, minWords: 250, criteria: ["Task Response", ...sharedCriteria] },
};

/** Biểu đồ cột của đề Task 1 (Đề tài 2.1: biểu đồ cho dưới dạng bảng số liệu). */
export type WritingChart = {
  /** Nhãn trục tung, kèm đơn vị. */
  unit: string;
  categories: string[];
  series: { name: string; values: number[] }[];
};

export type WritingExercise = ContentItemBase & {
  skill: "writing";
  task: WritingTask;
  /** Dạng đề, ví dụ Discussion. Chưa có cột riêng trong schema. */
  essayType: string | null;
  /** Đề bài đầy đủ. */
  prompt: string;
  /** Chỉ Task 1. */
  chart?: WritingChart;
  license: string;
  author: string;
};

export const writingExercises: WritingExercise[] = [
  {
    id: "wr-001",
    skill: "writing",
    task: "task2",
    essayType: "Discussion",
    prompt:
      "Many cities like Ho Chi Minh City are considering restricting motorbikes in the city centre. Discuss both views and give your opinion.",
    topic: "Transport",
    targetBand: 6.5,
    source: "self_written",
    license: "unconfirmed",
    author: "unconfirmed",
    status: "verified",
    model: null,
    promptVersion: null,
    createdAt: "2026-10-20T09:12:00+07:00",
    reportCount: 0,
  },
  {
    id: "wr-002",
    skill: "writing",
    task: "task1",
    essayType: "Bar chart",
    prompt:
      "The chart below shows the number of visitors to three museums in a city over four years. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.",
    chart: {
      unit: "Số khách (nghìn lượt)",
      categories: ["2021", "2022", "2023", "2024"],
      series: [
        { name: "History Museum", values: [34, 41, 52, 58] },
        { name: "Art Museum", values: [21, 25, 31, 36] },
        { name: "Science Museum", values: [12, 18, 27, 35] },
      ],
    },
    topic: "Tourism",
    targetBand: 6.0,
    source: "llm_generated_verified",
    license: "unconfirmed",
    author: "unconfirmed",
    // Để `verified` (trước là `spare`) để người học thấy thẻ và vào màn viết Task 1 (ui-rules #12).
    status: "verified",
    model: "gemini-flash",
    promptVersion: "writing-prompt-v1",
    createdAt: "2026-10-21T10:30:00+07:00",
    reportCount: 0,
  },
];

/** Tên thẻ ở Kho đề và tiêu đề trang làm bài (ui-rules #8): `Writing Task N: <topic>`. */
export function writingTitle(exercise: WritingExercise): string {
  return `Writing ${writingTaskInfo[exercise.task].label}: ${exercise.topic}`;
}

const sampleTask1Essay = `The bar chart compares the number of visitors to three museums in a city between 2021 and 2024, measured in thousands.

Overall, all three museums attracted more visitors over the period, and the History Museum remained the most popular throughout. The Science Museum showed the fastest growth.

In 2021, the History Museum received about 34,000 visitors, while the Art Museum and the Science Museum had 21,000 and 12,000 respectively. Over the next two years, the History Museum rose steadily to 52,000, and the Art Museum climbed to 31,000.

By 2024, the History Museum had reached 58,000 visitors. The Art Museum ended the period at 36,000, whereas the Science Museum have risen to 35,000, nearly three time its starting figure. As a result, the gap between the Art Museum and the Science Museum almost disappeared in the final year.

In summary, visitor numbers increased at every museum, but at different rates.`;

/** Vị trí trích dẫn theo code point, như backend tính. */
function quoteAt(quote: string) {
  const index = sampleTask1Essay.indexOf(quote);
  const start = Array.from(sampleTask1Essay.slice(0, index)).length;
  return { quote, start_char: start, end_char: start + Array.from(quote).length, verified: true };
}

function criterion(code: string, band: number, comment: string, quote: string) {
  return { criterion: code, band, comment, evidence: [quoteAt(quote)], descriptor_refs: [`SAMPLE-${code}`] };
}

const overview = "Overall, all three museums attracted more visitors over the period, and the History Museum remained the most popular throughout.";
const linking = "Over the next two years";
const comparison = "while the Art Museum and the Science Museum had 21,000 and 12,000 respectively";
const grammarSlip = "the Science Museum have risen to 35,000, nearly three time its starting figure";

const judgeA = [
  criterion("TR", 6.0, "Có câu tổng quan rõ.", overview),
  criterion("CC", 6.0, "Chia đoạn hợp lý.", linking),
  criterion("LR", 7.0, "Từ so sánh đa dạng.", comparison),
  criterion("GRA", 6.5, "Vài lỗi chia động từ.", grammarSlip),
];
const judgeB = [
  criterion("TR", 6.0, "Có câu tổng quan rõ.", overview),
  criterion("CC", 6.0, "Chia đoạn hợp lý.", linking),
  criterion("LR", 6.0, "Từ vựng đủ dùng, lặp lại nhiều.", comparison),
  criterion("GRA", 6.5, "Vài lỗi chia động từ.", grammarSlip),
];

/**
 * KẾT QUẢ MẪU cho màn kết quả Task 1, cùng hình dạng phản hồi của backend Writing (`POST /api/assess`).
 * Không phải điểm chấm bài của người học: backend chưa chấm Task 1 (chờ Người 4).
 */
export const sampleTask1Result: { essay: string; result: WritingAssessment } = {
  essay: sampleTask1Essay,
  result: {
    run_id: "run_sample_task1",
    attempt_id: "att_sample_task1",
    mode: "live",
    status: "final",
    overall_band: 6.0,
    word_count: 158,
    flags: [],
    judges: { A: { criteria: judgeA }, B: { criteria: judgeB } },
    criteria: [
      criterion("TR", 6.0, "Có câu tổng quan rõ; nêu đủ xu hướng chính.", overview),
      criterion("CC", 6.0, "Chia đoạn hợp lý, từ nối còn đơn giản.", linking),
      criterion("LR", 6.0, "Từ so sánh đúng nhưng lặp lại tên bảo tàng nhiều.", comparison),
      criterion("GRA", 6.5, "Câu phức đa dạng, còn lỗi chia động từ và số nhiều.", grammarSlip),
    ],
    reconciliation: { disputed: ["LR"], reason: "Xem comment và evidence của từng tiêu chí đối chiếu." },
    corrections: [
      { criterion: "GRA", error_code: "verb_tense", quote: "have risen", suggestion: "had risen", reason: "Mốc 2024 đã nói ở thì quá khứ hoàn thành." },
      { criterion: "GRA", error_code: "plural_noun", quote: "three time", suggestion: "three times", reason: "Sau số đếm dùng danh từ số nhiều." },
    ],
    limitations: [],
  },
};
