"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { HeadphonesIcon } from "@/components/icons";
import { formatClock } from "@/features/writing/text";
import type { TestMode } from "./attempt-store";
import type { AudioSegment } from "./result-view";
import { audioReducer, audioStatus, canPlay, canSeek, initialAudio, type AudioState, type SavedAudio } from "./audio-rules";

type AudioPlayerProps = {
  /** `null`: bài chưa có audio, khung vẫn giữ chỗ. */
  src: string | null;
  mode: TestMode;
  /** Số lần nghe, cờ nghe hết và cờ đã bắt đầu nghe đã lưu của lượt làm. */
  saved: SavedAudio;
  onProgress: (progress: SavedAudio) => void;
  /** Màn kết quả: phát đoạn này rồi dừng ở cuối đoạn; truyền object mới để phát lại cùng đoạn. */
  segment?: AudioSegment;
};

const frame = "glass flex flex-col gap-3 rounded-[28px] px-5 py-4";
const clock = (seconds: number) => formatClock(Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0)));

/** Trình phát Listening. Đổi `src` thì dựng lại từ đầu (tải lại file, trạng thái mới). */
export function AudioPlayer(props: AudioPlayerProps) {
  if (!props.src) {
    return (
      <section aria-label="Audio" className={frame}>
        <p className="flex min-h-11 items-center gap-3 text-[15px] text-muted">
          <HeadphonesIcon size={20} className="shrink-0" />
          Bài này chưa có audio
        </p>
      </section>
    );
  }
  return <LoadedPlayer key={props.src} {...props} src={props.src} />;
}

function LoadedPlayer({ src, mode, saved, onProgress, segment }: AudioPlayerProps & { src: string }) {
  const [state, dispatch] = useReducer(
    (s: AudioState, e: Parameters<typeof audioReducer>[2]) => audioReducer(mode, s, e),
    saved,
    (initial) => initialAudio(initial, mode),
  );
  // Thi đã khoá ngay lúc mở (nghe hết hoặc tải lại khi đang nghe dở): không tải file. Chốt một lần lúc mở.
  const [skipLoad] = useState(() => state.load === "skipped");
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loadRound, setLoadRound] = useState(0);
  const [time, setTime] = useState({ current: 0, duration: 0 });
  const audio = useRef<HTMLAudioElement>(null);
  const stopAt = useRef(Infinity);

  // Phát lại một đoạn; bấm khi file chưa tải xong thì phát ngay khi tải xong.
  useEffect(() => {
    const el = audio.current;
    if (!segment || !el) return;
    stopAt.current = segment.end_seconds;
    el.currentTime = segment.start_seconds;
    void el.play().catch(() => dispatch({ type: "pause" }));
  }, [segment, objectUrl]);

  // Tải trọn file trước khi cho phát (ui-rules mục 5); object URL được thu hồi khi unmount hoặc tải lại.
  useEffect(() => {
    if (skipLoad) return;
    const controller = new AbortController();
    let url: string | null = null;
    fetch(src, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status));
        return response.blob();
      })
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setObjectUrl(url);
        dispatch({ type: "loaded" });
      })
      .catch(() => {
        if (!controller.signal.aborted) dispatch({ type: "failed" });
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [src, loadRound, skipLoad]);

  const playable = canPlay(mode, state);
  const seekable = canSeek(mode);

  function toggle() {
    const el = audio.current;
    if (!el) return;
    if (state.playing) el.pause();
    else if (playable) void el.play().catch(() => dispatch({ type: "pause" }));
  }

  function played() {
    // Thi đã nghe hết: chặn mọi đường phát lại (phím media, menu trình duyệt).
    if (!playable) {
      audio.current?.pause();
      return;
    }
    dispatch({ type: "play" });
    // Lưu cờ đã bắt đầu nghe ngay lần Phát đầu: tải lại lúc đang nghe dở thì khoá.
    if (!state.started) onProgress({ plays: state.plays, finished: state.finished, started: true });
  }

  function ended() {
    const next = audioReducer(mode, state, { type: "ended" });
    dispatch({ type: "ended" });
    onProgress({ plays: next.plays, finished: next.finished, started: true });
  }

  const status = audioStatus(mode, state);

  return (
    <section aria-label="Audio" className={frame}>
      {objectUrl && (
        <audio
          ref={audio}
          src={objectUrl}
          preload="auto"
          onPlay={played}
          onPause={() => {
            stopAt.current = Infinity;
            dispatch({ type: "pause" });
          }}
          onEnded={ended}
          onLoadedMetadata={(e) => setTime({ current: 0, duration: e.currentTarget.duration })}
          onTimeUpdate={(e) => {
            if (e.currentTarget.currentTime >= stopAt.current) e.currentTarget.pause();
            setTime({ current: e.currentTarget.currentTime, duration: e.currentTarget.duration });
          }}
        />
      )}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={toggle}
          disabled={!state.playing && !playable}
          className="inline-flex min-h-11 min-w-[112px] items-center justify-center rounded-full bg-navy px-5 text-[15px] font-semibold text-cream focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy disabled:cursor-not-allowed disabled:opacity-50"
        >
          {state.playing ? "Tạm dừng" : seekable && time.duration > 0 && time.current >= time.duration ? "Nghe lại" : "Phát"}
        </button>
        {seekable ? (
          <input
            type="range"
            min={0}
            max={time.duration || 0}
            step={1}
            value={time.current}
            disabled={state.load !== "ready"}
            aria-label="Vị trí phát"
            aria-valuetext={`${clock(time.current)} trên ${clock(time.duration)}`}
            onChange={(e) => {
              if (audio.current) audio.current.currentTime = Number(e.target.value);
            }}
            className="h-11 min-w-0 flex-1 accent-navy"
          />
        ) : (
          <div aria-hidden="true" className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-navy/12">
            <div className="h-full rounded-full bg-orange" style={{ width: `${time.duration ? (time.current / time.duration) * 100 : 0}%` }} />
          </div>
        )}
        <span className="shrink-0 text-sm font-semibold text-muted">
          {clock(time.current)} / {clock(time.duration)}
        </span>
      </div>
      <p aria-live="polite" className="flex min-h-6 flex-wrap items-center gap-2 text-sm text-muted">
        {status}
        {state.load === "error" && (
          <button
            type="button"
            onClick={() => {
              dispatch({ type: "retry" });
              setLoadRound((n) => n + 1);
            }}
            className="min-h-11 font-semibold text-navy underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-navy"
          >
            Thử lại
          </button>
        )}
      </p>
    </section>
  );
}
