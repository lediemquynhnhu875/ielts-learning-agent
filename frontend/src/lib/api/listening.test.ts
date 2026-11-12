import { describe, expect, it } from "vitest";
import { audioUrl, getAudioTimings, getListeningTurns, loadListeningExtras } from "./listening";

const ID = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";
const turns = { speakers: [{ id: "speaker_1", label: "Host" }], turns: [{ position: 1, speaker_id: "speaker_1", text: "Hello.", start_char: 6, end_char: 12 }] };
const timings = {
  item_id: ID,
  audio_sha256: "abc",
  sample_rate: 24000,
  turns: [{ position: 1, speaker_id: "speaker_1", start_frame: 0, end_frame: 48000, start_seconds: 0, end_seconds: 2, source_start_char: 6, source_end_char: 12 }],
};

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

/** fetch giả: trả phản hồi theo đuôi đường dẫn; `null` là lỗi mạng. */
function fakeFetch(routes: { turns: Response | null; timings: Response | null }) {
  const calls: string[] = [];
  const fetchImpl = (async (url: string | URL | Request) => {
    calls.push(String(url));
    const response = String(url).endsWith("/audio/timings") ? routes.timings : routes.turns;
    if (!response) throw new TypeError("network");
    return response;
  }) as typeof fetch;
  return { calls, fetchImpl };
}

describe("listening client", () => {
  it("gọi đúng route trung gian", async () => {
    const api = fakeFetch({ turns: json(200, turns), timings: json(200, timings) });
    expect(await getListeningTurns(ID, api.fetchImpl)).toEqual(turns);
    expect(await getAudioTimings(ID, api.fetchImpl)).toEqual(timings);
    expect(api.calls).toEqual([`/api/backend/exercises/${ID}/listening-turns`, `/api/backend/exercises/${ID}/audio/timings`]);
    expect(audioUrl(ID)).toBe(`/api/backend/exercises/${ID}/audio`);
  });
});

describe("loadListeningExtras", () => {
  it("có audio đã kiểm chứng: url qua route trung gian, mốc lượt nói từ timings, kèm lượt người nói", async () => {
    const api = fakeFetch({ turns: json(200, turns), timings: json(200, timings) });
    expect(await loadListeningExtras(ID, api.fetchImpl)).toEqual({
      audio: { url: `/api/backend/exercises/${ID}/audio`, turns: [{ start_seconds: 0, end_seconds: 2, source_start_char: 6, source_end_char: 12 }] },
      turns,
    });
  });

  it("409 audio_not_verified: không có audio (rơi về trạng thái chưa có audio), vẫn có lượt người nói", async () => {
    const api = fakeFetch({ turns: json(200, turns), timings: json(409, { error: "audio_not_verified", message: "Audio is not verified" }) });
    expect(await loadListeningExtras(ID, api.fetchImpl)).toEqual({ audio: null, turns });
  });

  it("404, 503 hoặc lỗi mạng: không ném lỗi, không có audio và không có lượt người nói", async () => {
    expect(await loadListeningExtras(ID, fakeFetch({ turns: json(404, { detail: "Exercise not found" }), timings: json(404, { detail: "Not Found" }) }).fetchImpl)).toEqual({ audio: null, turns: null });
    expect(await loadListeningExtras(ID, fakeFetch({ turns: json(422, { detail: "Exercise must be a Listening item" }), timings: json(503, { error: "audio_not_configured" }) }).fetchImpl)).toEqual({ audio: null, turns: null });
    expect(await loadListeningExtras(ID, fakeFetch({ turns: null, timings: null }).fetchImpl)).toEqual({ audio: null, turns: null });
  });

  it("phản hồi sai hình dạng coi như không có", async () => {
    const api = fakeFetch({ turns: json(200, { speakers: "x" }), timings: json(200, { turns: "x" }) });
    expect(await loadListeningExtras(ID, api.fetchImpl)).toEqual({ audio: null, turns: null });
  });
});
