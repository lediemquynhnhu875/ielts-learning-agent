import { describe, expect, it } from "vitest";
import { audioOf, audioReducer, audioStatus, canPlay, canSeek, initialAudio, scriptVisibility, type AudioState } from "./audio-rules";

const fresh = { plays: 0, finished: false, started: false };
const ready = (extra: Partial<AudioState> = {}): AudioState => ({ ...initialAudio(fresh, "mock"), load: "ready", ...extra });

describe("audioReducer · chế độ Thi", () => {
  it("phát, tạm dừng, phát tiếp được", () => {
    let s = audioReducer("mock", ready(), { type: "play" });
    expect(s.playing).toBe(true);
    s = audioReducer("mock", s, { type: "pause" });
    expect(s.playing).toBe(false);
    expect(canPlay("mock", s)).toBe(true);
  });

  it("hết bài thì khoá: không phát lại được, cờ nghe hết bật", () => {
    const s = audioReducer("mock", ready({ playing: true }), { type: "ended" });
    expect(s).toMatchObject({ playing: false, finished: true, plays: 1 });
    expect(canPlay("mock", s)).toBe(false);
    expect(audioReducer("mock", s, { type: "play" }).playing).toBe(false);
  });

  it("đọc lại cờ đã lưu: mở lại trang vẫn khoá", () => {
    const s = { ...initialAudio({ plays: 1, finished: true, started: true }, "mock"), load: "ready" as const };
    expect(canPlay("mock", s)).toBe(false);
    expect(audioStatus("mock", s)).toBe("Bạn đã nghe hết bài");
  });

  it("bấm Phát thì bật cờ đã bắt đầu nghe", () => {
    expect(ready().started).toBe(false);
    expect(audioReducer("mock", ready(), { type: "play" }).started).toBe(true);
  });

  it("tải lại trang lúc đang nghe dở: coi như đã nghe, khoá và báo đã dùng lượt nghe", () => {
    const s = initialAudio({ plays: 0, finished: false, started: true }, "mock");
    expect(s.finished).toBe(true);
    expect(canPlay("mock", { ...s, load: "ready" })).toBe(false);
    expect(audioStatus("mock", s)).toBe("Bạn đã dùng lượt nghe");
  });

  it("đã khoá từ đầu thì không tải audio", () => {
    expect(initialAudio({ plays: 0, finished: false, started: true }, "mock").load).toBe("skipped");
    expect(initialAudio({ plays: 1, finished: true, started: true }, "mock").load).toBe("skipped");
    expect(initialAudio(fresh, "mock").load).toBe("loading");
  });

  it("không tua", () => {
    expect(canSeek("mock")).toBe(false);
  });
});

describe("audioReducer · chế độ Luyện", () => {
  it("nghe hết vẫn phát lại được và đếm số lần", () => {
    let s = audioReducer("practice", ready({ playing: true }), { type: "ended" });
    expect(canPlay("practice", s)).toBe(true);
    s = audioReducer("practice", audioReducer("practice", s, { type: "play" }), { type: "ended" });
    expect(s.plays).toBe(2);
    expect(canSeek("practice")).toBe(true);
    expect(audioStatus("practice", s)).toBe("Đã nghe 2 lần");
  });

  it("cờ đã bắt đầu nghe không khoá chế độ Luyện", () => {
    const s = initialAudio({ plays: 0, finished: false, started: true }, "practice");
    expect(s.load).toBe("loading");
    expect(canPlay("practice", { ...s, load: "ready" })).toBe(true);
  });
});

describe("audioReducer · tải file", () => {
  it("chưa tải xong thì chưa phát được; lỗi rồi thử lại về đang tải", () => {
    const loading = initialAudio(fresh, "practice");
    expect(loading.load).toBe("loading");
    expect(canPlay("practice", loading)).toBe(false);
    const failed = audioReducer("practice", loading, { type: "failed" });
    expect(failed.load).toBe("error");
    expect(audioReducer("practice", failed, { type: "retry" }).load).toBe("loading");
    expect(audioReducer("practice", loading, { type: "loaded" }).load).toBe("ready");
    expect(audioReducer("practice", loading, { type: "play" }).playing).toBe(false);
    expect(audioStatus("practice", loading)).toBe("Đang tải audio…");
    expect(audioStatus("practice", failed)).toBe("Không tải được audio");
    expect(audioStatus("mock", { ...loading, load: "ready" })).toBe("");
  });
});

describe("audioOf", () => {
  it("chỉ nhận audio có url chuỗi; turns hỏng bị bỏ", () => {
    expect(audioOf({})).toBeNull();
    expect(audioOf({ audio: { url: "" } })).toBeNull();
    expect(audioOf({ audio: { url: 3 } })).toBeNull();
    expect(audioOf({ audio: { url: "/a.mp3" } })).toEqual({ url: "/a.mp3", turns: [] });
    const turns = [
      { start_seconds: 0, end_seconds: 2, source_start_char: 6, source_end_char: 9 },
      { start_seconds: "x", end_seconds: 1, source_start_char: 0, source_end_char: 2 },
      { start_s: 0, end_s: 2, text: "kiểu cũ" },
    ];
    expect(audioOf({ audio: { url: "/a.mp3", turns } })).toEqual({ url: "/a.mp3", turns: [turns[0]] });
  });
});

describe("scriptVisibility", () => {
  it("Luyện có audio: có nút Xem script (script ẩn mặc định), không có băng báo", () => {
    expect(scriptVisibility("practice", true, false)).toEqual({ available: true, noAudioNotice: false });
    expect(scriptVisibility("practice", true, true)).toEqual({ available: true, noAudioNotice: false });
  });

  it("Thi có audio: lúc làm bài không có script, sau khi nộp mới có nút", () => {
    expect(scriptVisibility("mock", true, false)).toEqual({ available: false, noAudioNotice: false });
    expect(scriptVisibility("mock", true, true)).toEqual({ available: true, noAudioNotice: false });
  });

  it("chưa có audio (cả hai chế độ): có nút kèm băng báo lúc làm bài; đã nộp thì chỉ còn nút", () => {
    expect(scriptVisibility("practice", false, false)).toEqual({ available: true, noAudioNotice: true });
    expect(scriptVisibility("mock", false, false)).toEqual({ available: true, noAudioNotice: true });
    expect(scriptVisibility("mock", false, true)).toEqual({ available: true, noAudioNotice: false });
  });
});
