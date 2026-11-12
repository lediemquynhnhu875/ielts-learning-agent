import { describe, expect, it } from "vitest";
import type { AnswerMap } from "@/lib/api/attempts";
import { createAnswerDraft, type SaveStatus } from "./answer-draft";

/** Đồng hồ giả: giữ hàm hẹn, test tự gọi `fire()`. */
function fakeTimer() {
  let pending: { fn: () => void; ms: number } | null = null;
  return {
    setTimer: (fn: () => void, ms: number) => {
      pending = { fn, ms };
      return pending;
    },
    clearTimer: (handle: unknown) => {
      if (handle === pending) pending = null;
    },
    get delay() {
      return pending?.ms ?? null;
    },
    fire() {
      const current = pending;
      pending = null;
      current?.fn();
    },
  };
}

type Deferred = { resolve: () => void; reject: (e: unknown) => void };

function setup() {
  const timer = fakeTimer();
  const sent: AnswerMap[] = [];
  const calls: Deferred[] = [];
  const statuses: SaveStatus[] = [];
  const errors: unknown[] = [];
  const draft = createAnswerDraft({
    save: (answers) =>
      new Promise<void>((resolve, reject) => {
        sent.push(answers);
        calls.push({ resolve, reject });
      }),
    setTimer: timer.setTimer,
    clearTimer: timer.clearTimer,
    onStatus: (status, error) => {
      statuses.push(status);
      if (error !== undefined) errors.push(error);
    },
  });
  return { timer, sent, calls, statuses, errors, draft };
}

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("createAnswerDraft", () => {
  it("gom thay đổi và chỉ gửi sau 1 giây ngưng thao tác", async () => {
    const { timer, sent, calls, statuses, draft } = setup();
    draft.change("q1", "A");
    draft.change("q2", "TRUE");
    draft.change("q1", "B");
    expect(timer.delay).toBe(1000);
    expect(sent).toHaveLength(0);
    expect(statuses.at(-1)).toBe("pending");

    timer.fire();
    expect(sent).toEqual([{ q1: "B", q2: "TRUE" }]);
    expect(statuses.at(-1)).toBe("saving");
    calls[0].resolve();
    await tick();
    expect(statuses.at(-1)).toBe("saved");
  });

  it("ô trống hoặc chỉ có khoảng trắng gửi null", () => {
    const { timer, sent, draft } = setup();
    draft.change("q1", "");
    draft.change("q2", "   ");
    timer.fire();
    expect(sent).toEqual([{ q1: null, q2: null }]);
  });

  it("mỗi request tối đa 40 câu, phần còn lại gửi tiếp", async () => {
    const { timer, sent, calls, draft } = setup();
    for (let i = 0; i < 45; i++) draft.change(`q${i}`, "A");
    timer.fire();
    expect(Object.keys(sent[0])).toHaveLength(40);
    calls[0].resolve();
    await tick();
    expect(Object.keys(sent[1])).toHaveLength(5);
  });

  it("lỗi thì báo Lưu lỗi kèm lỗi, giữ thay đổi; thử lại gửi lại đúng thay đổi đó", async () => {
    const { timer, sent, calls, statuses, errors, draft } = setup();
    draft.change("q1", "A");
    timer.fire();
    calls[0].reject(new Error("mất mạng"));
    await tick();
    expect(statuses.at(-1)).toBe("error");
    expect(errors).toHaveLength(1);

    void draft.retry();
    expect(sent[1]).toEqual({ q1: "A" });
    calls[1].resolve();
    await tick();
    expect(statuses.at(-1)).toBe("saved");
  });

  it("lỗi không ghi đè thay đổi mới hơn của cùng câu", async () => {
    const { timer, sent, calls, draft } = setup();
    draft.change("q1", "A");
    timer.fire();
    draft.change("q1", "B");
    calls[0].reject(new Error("x"));
    await tick();
    void draft.flush();
    expect(sent[1]).toEqual({ q1: "B" });
  });

  it("thay đổi trong lúc đang lưu thì đợi hẹn giờ mới, không gửi ngay", async () => {
    const { timer, sent, calls, statuses, draft } = setup();
    draft.change("q1", "A");
    timer.fire();
    draft.change("q2", "B");
    calls[0].resolve();
    await tick();
    expect(sent).toHaveLength(1);
    expect(statuses.at(-1)).toBe("pending");
    timer.fire();
    expect(sent[1]).toEqual({ q2: "B" });
  });

  it("flush gửi ngay và trả về true khi lưu được", async () => {
    const { timer, sent, calls, draft } = setup();
    draft.change("q1", "A");
    const done = draft.flush();
    expect(timer.delay).toBeNull();
    expect(sent).toEqual([{ q1: "A" }]);
    calls[0].resolve();
    expect(await done).toBe(true);
  });

  it("close huỷ hẹn giờ, bỏ thay đổi chưa gửi và không báo trạng thái nữa", async () => {
    const { timer, sent, calls, statuses, draft } = setup();
    draft.change("q1", "A");
    timer.fire();
    draft.change("q2", "B");
    draft.close();
    expect(timer.delay).toBeNull();
    const before = statuses.length;
    calls[0].reject(new Error("409"));
    await tick();
    expect(statuses.length).toBe(before);
    draft.change("q3", "C");
    expect(timer.delay).toBeNull();
    expect(sent).toHaveLength(1);
  });
});
