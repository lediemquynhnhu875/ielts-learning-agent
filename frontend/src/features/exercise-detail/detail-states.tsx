import Link from "next/link";
import { ChevronLeftIcon } from "@/components/icons";

/** Khung chờ khi trang chi tiết đang tải bài từ backend. */
export function DetailSkeleton() {
  const block = "glass animate-pulse rounded-[26px] motion-reduce:animate-none";
  return (
    <div aria-busy="true" aria-label="Đang tải bài" className="flex flex-col gap-5">
      <div className={`${block} h-[132px] rounded-[32px]`} />
      <div className="grid grid-cols-1 items-start gap-5 min-[1150px]:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col gap-5">
          <div className={`${block} h-[320px]`} />
          <div className={`${block} h-[220px]`} />
        </div>
        <div className="flex flex-col gap-5">
          <div className={`${block} h-[330px]`} />
          <div className={`${block} h-[120px]`} />
        </div>
      </div>
    </div>
  );
}

/** Không tải được bài (backend tắt, CSDL chưa sẵn sàng, token sai…). Bài không tồn tại thì dùng trang 404. */
export function DetailError({ message }: { message: string }) {
  return (
    <section role="alert" className="glass flex flex-col items-start gap-3 rounded-[32px] px-8 py-8">
      <h1 className="text-2xl font-extrabold tracking-tight">Không tải được bài</h1>
      <p className="text-[15px] text-muted">{message}</p>
      <Link
        href="/exercises"
        className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-navy px-[18px] py-2.5 text-sm font-semibold text-cream"
      >
        <ChevronLeftIcon size={16} />
        Về Kho đề
      </Link>
    </section>
  );
}
