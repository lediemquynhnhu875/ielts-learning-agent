/**
 * DỮ LIỆU GIẢ LẬP (mock) cho bộ đề Speaking, chưa lấy từ backend.
 * Bộ "part2-skill" lấy từ docs/speaking/examples/database-export-text.json
 * (target_band = null, status = spare, source = self_written).
 */
import type { ContentItemBase } from "./types";

export type SpeakingExercise = ContentItemBase & {
  skill: "speaking";
  part1: string[];
  part2: { cue: string; points: string[]; explain: string | null };
  part3: string[];
  license: string;
  author: string;
};

export const speakingExercises: SpeakingExercise[] = [
  {
    id: "sp-001",
    skill: "speaking",
    topic: "part2-skill",
    targetBand: null,
    source: "self_written",
    license: "unconfirmed",
    author: "unconfirmed",
    status: "spare",
    model: null,
    promptVersion: null,
    createdAt: "2026-10-15T18:08:36Z",
    reportCount: 0,
    part1: [
      "Do you work or are you a student?",
      "What do you enjoy most about your studies or your work?",
      "Can you tell me about the place where you live?",
      "What do you like most about your hometown?",
    ],
    part2: {
      cue: "Describe a skill you learned that is useful to you.",
      points: ["what the skill is", "when and how you learned it", "how you use it now"],
      explain: "and explain why this skill is important to you.",
    },
    part3: [
      "Why is learning useful skills important in society today?",
      "How might this differ between younger and older generations?",
      "How would society change if the opposite were true?",
    ],
  },
];
