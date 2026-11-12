import Link from "next/link";
import { ChevronLeftIcon } from "@/components/icons";

/** Khối báo một dòng kèm đường về Kho đề. */
function Notice({ title, line }: { title: string; line?: string }) {
  return (
    <section className="glass flex flex-col items-start gap-3 rounded-[32px] px-8 py-8">
      <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
      {line && <p className="text-[15px] text-muted">{line}</p>}
      <Link
        href="/exercises"
        className="mt-1 inline-flex min-h-11 items-center gap-1.5 rounded-full bg-navy px-[18px] text-sm font-semibold text-cream focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
      >
        <ChevronLeftIcon size={16} />
        Về Kho đề
      </Link>
    </section>
  );
}

/** Người không phải người học (giáo viên, chưa đăng nhập) mở trang Thi thử. */
export function LearnerOnly() {
  return <Notice title="Trang này dành cho người học" />;
}

/** Người học mở bài mẫu (id không phải UUID): chưa có lượt làm ở backend. */
export function SampleOnly({ title }: { title: string }) {
  return <Notice title={title} line="Bài mẫu, chưa làm được" />;
}
