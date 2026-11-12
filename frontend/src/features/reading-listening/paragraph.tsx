import { Fragment } from "react";

/** Đoạn văn tách bằng dòng trống, cùng cách tách với trang chi tiết bài. */
export const splitParagraphs = (text: string) => text.split(/\n\s*\n/);

/** Nhãn đoạn `[A] ` ở đầu đoạn. */
export const PARAGRAPH_LABEL = /^\[([A-Z])\]\s*/;

const paragraphClass = "mt-3 max-w-[68ch] text-base leading-[1.8] first:mt-0";
const markClass = "rounded-[5px] bg-orange/50 px-[3px] py-0.5 text-inherit";

/** Nút mở/thu script Listening, dùng ở màn làm bài và màn kết quả; script luôn thu gọn mặc định. */
export function ScriptToggle({ open, onToggle, controls }: { open: boolean; onToggle: () => void; controls: string }) {
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={controls}
      onClick={onToggle}
      className="inline-flex min-h-11 items-center justify-center self-start rounded-full border border-navy/25 bg-white/70 px-5 text-[15px] font-semibold hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
    >
      {open ? "Ẩn script" : "Xem script"}
    </button>
  );
}

/** Một khối đã tách nhãn (blocks.ts): đoạn văn nhãn A, B… hoặc lượt nói có tên; tô đúng khoảng `range` nếu có. */
export function BlockParagraph({ label, text, range }: { label: string | null; text: string; range: [number, number] | null }) {
  return (
    <p className={paragraphClass}>
      {label && (label.length === 1 ? <b className="mr-2.5 text-lg text-navy">{label}</b> : <b className="mr-2 text-navy">{label}:</b>)}
      {range ? (
        <>
          {text.slice(0, range[0])}
          <mark className={markClass}>{text.slice(range[0], range[1])}</mark>
          {text.slice(range[1])}
        </>
      ) : (
        text
      )}
    </p>
  );
}

/** Một đoạn văn: tách nhãn [A] thành chữ đậm, tô cam phần bằng chứng nếu có. */
export function Paragraph({ text, highlight, faded = false }: { text: string; highlight: string | null; faded?: boolean }) {
  const match = text.match(PARAGRAPH_LABEL);
  const label = match?.[1];
  const body = match ? text.slice(match[0].length) : text;
  const parts = highlight && body.includes(highlight) ? body.split(highlight) : [body];

  return (
    <p className={`${paragraphClass} ${faded ? "text-navy-deep/55" : ""}`}>
      {label && <b className="mr-2.5 text-lg text-navy">{label}</b>}
      {parts.map((part, i) => (
        <Fragment key={i}>
          {part}
          {i < parts.length - 1 && (
            <mark className={markClass}>{highlight}</mark>
          )}
        </Fragment>
      ))}
    </p>
  );
}
