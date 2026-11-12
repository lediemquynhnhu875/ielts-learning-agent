import { describe, expect, it } from "vitest";
import { toPlayable } from "./playable";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";
const base = { id: ID, skill: "reading" as const, title: "Mangroves", status: "verified" as const };

describe("toPlayable", () => {
  it("bài Reading/Listening verified chỉ trả id, skill, title", () => {
    expect(toPlayable(base)).toEqual({ id: ID, skill: "reading", title: "Mangroves" });
    expect(toPlayable({ ...base, skill: "listening" })?.skill).toBe("listening");
  });

  it("bài chưa verified hoặc kỹ năng khác thì không làm được", () => {
    expect(toPlayable({ ...base, status: "spare" })).toBeNull();
    expect(toPlayable({ ...base, status: "rejected" })).toBeNull();
    expect(toPlayable({ ...base, skill: "writing" as "reading" })).toBeNull();
  });
});
