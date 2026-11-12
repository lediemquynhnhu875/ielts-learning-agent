import { SearchIcon } from "@/components/icons";
import { skillVisual } from "./skill-visual";

type BankHeaderProps = {
  /** Tên trang; mặc định "Kho đề". */
  title?: string;
  query: string;
  onQueryChange: (value: string) => void;
};

/** Vị trí 4 ô kỹ năng trong cụm icon (300×118px); tâm cụm trùng tâm khung. */
const tiles = [
  { skill: "reading", pos: "left-0 top-2 size-[72px] rotate-[-9deg] rounded-[23px] shadow-[0_14px_30px_rgb(33_61_104/0.3)]" },
  { skill: "listening", pos: "left-[92px] top-[46px] size-[72px] rotate-[7deg] rounded-[23px] shadow-[0_14px_30px_rgb(232_150_63/0.35)]" },
  { skill: "writing", pos: "left-[176px] top-0 size-[72px] rotate-[-5deg] rounded-[23px] shadow-[0_14px_30px_rgb(58_99_168/0.35)]" },
  { skill: "speaking", pos: "left-[234px] top-[52px] size-16 rotate-[9deg] rounded-[21px] shadow-[0_14px_30px_rgb(138_66_16/0.35)]" },
] as const;

/** Khối tiêu đề kính: bên trái tên trang + ô tìm bài, bên phải 4 ô kỹ năng nghiêng; hai cụm căn giữa theo chiều cao. */
export function BankHeader({ title = "Kho đề", query, onQueryChange }: BankHeaderProps) {
  return (
    <section className="glass relative flex min-h-[150px] items-center justify-between gap-6 overflow-hidden rounded-[30px] px-6 py-5 sm:px-9">
      <div
        aria-hidden="true"
        className="absolute -right-[60px] -top-20 size-[360px] rounded-full bg-[radial-gradient(circle_at_40%_40%,rgb(247_184_115/0.9),rgb(235_164_94/0.35)_60%,transparent_72%)]"
      />

      <div className="relative flex w-full max-w-[460px] flex-col gap-3.5">
        <h1 className="text-[32px] font-extrabold leading-tight tracking-[-0.025em] sm:text-[38px]">{title}</h1>
        <label className="flex w-full items-center gap-3 rounded-full border border-white bg-white/85 px-5 py-3 text-muted shadow-[0_8px_24px_rgb(33_61_104/0.1)]">
          <SearchIcon />
          <input
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Tìm bài"
            aria-label="Tìm bài"
            className="w-full bg-transparent text-[15px] text-navy-deep outline-none placeholder:text-muted"
          />
        </label>
      </div>

      <div aria-hidden="true" className="relative hidden h-[118px] w-[300px] shrink-0 min-[1150px]:block">
        {tiles.map(({ skill, pos }) => {
          const { icon: Icon, tile } = skillVisual[skill];
          return (
            <span key={skill} className={`absolute grid place-items-center ${tile} ${pos}`}>
              <Icon size={skill === "speaking" ? 30 : 33} />
            </span>
          );
        })}
      </div>
    </section>
  );
}
