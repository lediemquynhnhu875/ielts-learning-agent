import { describe, expect, it } from "vitest";
import type { AttemptExercise, AttemptQuestionGroup } from "@/lib/api/attempts";
import { choicesFor, chunkAnswers, CLASSIFICATIONS, groupedQuestions, groupsOf, instructionsShown, stripRepeatedLimit, toAnswerMap, unansweredCount } from "./questions";

const q = (id: string, number: number, options: Record<string, string> = {}) => ({ id, position: number, number, prompt: `Q${number}`, options, target: {} });

const group = (extra: Partial<AttemptQuestionGroup>): AttemptQuestionGroup => ({
  group_id: "g",
  position: 1,
  question_type: "multiple_choice",
  instructions: "",
  response_mode: "options",
  options: {},
  response_limits: {},
  allow_reuse: false,
  questions: [],
  ...extra,
});

describe("groupsOf", () => {
  it("sắp nhóm và câu theo position", () => {
    const exercise = {
      question_groups: [
        group({ group_id: "b", position: 2, questions: [q("q3", 3)] }),
        group({ group_id: "a", position: 1, questions: [q("q2", 2), q("q1", 1)].map((x, i) => ({ ...x, position: 2 - i })) }),
      ],
    } as unknown as AttemptExercise;
    const groups = groupsOf(exercise);
    expect(groups.map((g) => g.group_id)).toEqual(["a", "b"]);
    expect(groups[0].questions.map((x) => x.id)).toEqual(["q1", "q2"]);
  });
});

describe("groupedQuestions", () => {
  const tfng = { question_type: "true_false_not_given" as const, response_mode: "classification" as const, instructions: "Write TRUE, FALSE or NOT GIVEN." };
  const mcq = { instructions: "Choose the correct letter." };
  const fill = { question_type: "sentence_completion" as const, response_mode: "text" as const, instructions: "Complete the sentences.", response_limits: { max_words: 2 } };
  // Listening do backend sinh xen kẽ: T/F/NG, trắc nghiệm, điền từ, rồi lặp lại; mỗi câu một nhóm.
  const interleaved = {
    question_groups: [
      group({ ...tfng, group_id: "g1", position: 1, questions: [q("q1", 1)] }),
      group({ ...mcq, group_id: "g2", position: 2, options: { A: "a2" }, questions: [q("q2", 2)] }),
      group({ ...fill, group_id: "g3", position: 3, questions: [q("q3", 3)] }),
      group({ ...tfng, group_id: "g4", position: 4, questions: [q("q4", 4)] }),
      group({ ...mcq, group_id: "g5", position: 5, options: { B: "b5" }, questions: [q("q5", 5)] }),
      group({ ...fill, group_id: "g6", position: 6, questions: [q("q6", 6)] }),
    ],
  } as unknown as AttemptExercise;

  it("gom các câu cùng dạng và hướng dẫn thành một nhóm, nhóm theo thứ tự xuất hiện đầu tiên", () => {
    const groups = groupedQuestions(interleaved);
    expect(groups.map((g) => g.question_type)).toEqual(["true_false_not_given", "multiple_choice", "sentence_completion"]);
    expect(groups.map((g) => g.questions.map((x) => x.id))).toEqual([["q1", "q4"], ["q2", "q5"], ["q3", "q6"]]);
  });

  it("đánh số lại 1..N theo thứ tự hiển thị; id câu giữ nguyên", () => {
    const flat = groupedQuestions(interleaved).flatMap((g) => g.questions);
    expect(flat.map((x) => x.number)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(flat.map((x) => x.id)).toEqual(["q1", "q4", "q2", "q5", "q3", "q6"]);
  });

  it("câu trắc nghiệm không có lựa chọn riêng giữ lựa chọn của nhóm gốc khi bị gom", () => {
    const [, mc] = groupedQuestions(interleaved);
    expect(choicesFor(mc, mc.questions[0]).map((c) => c.value)).toEqual(["A"]);
    expect(choicesFor(mc, mc.questions[1]).map((c) => c.value)).toEqual(["B"]);
  });

  it("khác hướng dẫn hoặc giới hạn từ thì không gom", () => {
    const ex = {
      question_groups: [
        group({ ...fill, group_id: "a", position: 1, questions: [q("q1", 1)] }),
        group({ ...fill, group_id: "b", position: 2, response_limits: { max_words: 3 }, questions: [q("q2", 2)] }),
        group({ ...fill, group_id: "c", position: 3, instructions: "Other.", questions: [q("q3", 3)] }),
      ],
    } as unknown as AttemptExercise;
    expect(groupedQuestions(ex)).toHaveLength(3);
  });

  it("đề đã gom sẵn (Reading) giữ nguyên thứ tự và số câu; không sửa dữ liệu gốc", () => {
    const reading = {
      question_groups: [
        group({ ...tfng, group_id: "a", position: 1, questions: [q("q1", 1), q("q2", 2)] }),
        group({ ...mcq, group_id: "b", position: 2, questions: [q("q3", 3)] }),
      ],
    } as unknown as AttemptExercise;
    const flat = groupedQuestions(reading).flatMap((g) => g.questions);
    expect(flat.map((x) => [x.id, x.number])).toEqual([["q1", 1], ["q2", 2], ["q3", 3]]);
    expect(interleaved.question_groups[3].questions[0].number).toBe(4);
  });
});

describe("choicesFor", () => {
  it("T/F/NG gửi đúng TRUE, FALSE, NOT GIVEN", () => {
    expect(CLASSIFICATIONS).toEqual(["TRUE", "FALSE", "NOT GIVEN"]);
    const g = group({ response_mode: "classification", question_type: "true_false_not_given" });
    expect(choicesFor(g, q("q1", 1)).map((c) => c.value)).toEqual(["TRUE", "FALSE", "NOT GIVEN"]);
  });

  it("trắc nghiệm dùng lựa chọn của câu, gửi nhãn A, B…", () => {
    const g = group({ options: { X: "nhóm" } });
    expect(choicesFor(g, q("q1", 1, { A: "Một", B: "Hai" }))).toEqual([
      { value: "A", text: "Một" },
      { value: "B", text: "Hai" },
    ]);
  });

  it("câu không có lựa chọn riêng thì dùng lựa chọn của nhóm (matching)", () => {
    const g = group({ question_type: "matching_headings", options: { i: "Heading one", ii: "Heading two" } });
    expect(choicesFor(g, q("q1", 1)).map((c) => c.value)).toEqual(["i", "ii"]);
  });
});

describe("instructionsShown", () => {
  const mcq = "Choose ONE correct option for each question.";
  const tfng = "Write TRUE, FALSE or NOT GIVEN for each statement.";

  it("nhóm liền trước cùng instructions và response_mode thì không hiện lại", () => {
    const groups = [
      group({ instructions: tfng, response_mode: "classification" }),
      group({ instructions: mcq }),
      group({ instructions: mcq }),
      group({ instructions: mcq }),
    ];
    expect(instructionsShown(groups)).toEqual([true, true, false, false]);
  });

  it("cùng instructions nhưng khác response_mode thì vẫn hiện", () => {
    expect(instructionsShown([group({ instructions: mcq }), group({ instructions: mcq, response_mode: "text" })])).toEqual([true, true]);
  });

  it("cùng instructions nhưng không liền nhau thì hiện lại", () => {
    const groups = [group({ instructions: mcq }), group({ instructions: tfng, response_mode: "classification" }), group({ instructions: mcq })];
    expect(instructionsShown(groups)).toEqual([true, true, true]);
  });

  it("nhóm đầu luôn hiện; nhóm không có instructions thì không hiện", () => {
    expect(instructionsShown([group({ instructions: mcq })])).toEqual([true]);
    expect(instructionsShown([group({ instructions: "" }), group({ instructions: "" })])).toEqual([false, false]);
    expect(instructionsShown([])).toEqual([]);
  });
});

describe("stripRepeatedLimit", () => {
  const instructions = "Complete each sentence. Write NO MORE THAN TWO WORDS from the text.";

  it("nhóm đã nêu giới hạn từ: bỏ câu giới hạn lặp lại ở cuối prompt (passage và text)", () => {
    expect(stripRepeatedLimit("Roof gardens need a ____. Write NO MORE THAN TWO WORDS from the passage.", instructions)).toBe("Roof gardens need a ____.");
    expect(stripRepeatedLimit("Soil is kept ____. Write NO MORE THAN TWO WORDS from the text.", instructions)).toBe("Soil is kept ____.");
  });

  it("không phân biệt chữ hoa/thường", () => {
    expect(stripRepeatedLimit("Water drains to the ____. write no more than two words from the Passage.", instructions.toLowerCase())).toBe("Water drains to the ____.");
  });

  it("prompt không có câu lặp thì giữ nguyên", () => {
    expect(stripRepeatedLimit("Roof gardens need a ____.", instructions)).toBe("Roof gardens need a ____.");
  });

  it("nhóm chưa nêu giới hạn từ thì giữ nguyên prompt", () => {
    const prompt = "Roof gardens need a ____. Write NO MORE THAN TWO WORDS from the passage.";
    expect(stripRepeatedLimit(prompt, "Complete each sentence.")).toBe(prompt);
  });

  it("câu giới hạn không nằm ở cuối prompt thì không đụng tới", () => {
    const prompt = "Write NO MORE THAN TWO WORDS from the passage. Roof gardens need a ____.";
    expect(stripRepeatedLimit(prompt, instructions)).toBe(prompt);
  });
});

describe("toAnswerMap và unansweredCount", () => {
  it("gửi mọi câu, ô trống hoặc khoảng trắng là null", () => {
    expect(toAnswerMap(["q1", "q2", "q3"], { q1: "A", q2: "  " })).toEqual({ q1: "A", q2: null, q3: null });
  });

  it("chia đáp án thành lô tối đa 40 câu", () => {
    const map = Object.fromEntries(Array.from({ length: 85 }, (_, i) => [`q${i}`, "A"]));
    expect(chunkAnswers(map).map((c) => Object.keys(c).length)).toEqual([40, 40, 5]);
    expect(chunkAnswers({})).toEqual([]);
  });

  it("đếm câu còn trống", () => {
    expect(unansweredCount(["q1", "q2", "q3"], { q1: "A", q2: " " })).toBe(2);
  });
});
