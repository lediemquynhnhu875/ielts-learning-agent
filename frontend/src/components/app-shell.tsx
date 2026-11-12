import type { ReactNode } from "react";
import { Sidebar } from "@/components/sidebar/sidebar";
import { mockReportCount, mockSession } from "@/mock-data/session";

/** Khung trang: nền, mảng màu mờ và thanh bên. Mảng màu nằm dưới vùng nội dung, không đặt sau thanh bên. */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen overflow-x-clip">
      <div aria-hidden="true" className="pointer-events-none fixed inset-0">
        <div className="absolute -right-36 -top-52 size-[560px] rounded-full bg-[radial-gradient(circle_at_35%_35%,#f7b873,#eba45e_55%,transparent_72%)] opacity-80 blur-[70px]" />
        <div className="absolute left-[280px] top-[330px] size-[420px] rounded-full bg-orange opacity-55 blur-[60px]" />
        <div className="absolute left-[520px] top-[620px] size-[520px] rounded-full bg-sky opacity-45 blur-[60px]" />
        <div className="absolute -bottom-16 right-32 size-[380px] rounded-full bg-orange-light opacity-55 blur-[60px]" />
      </div>
      <div className="relative flex gap-3 p-3 md:gap-7 md:p-6">
        <Sidebar user={mockSession} reportCount={mockReportCount} />
        <main className="min-w-0 flex-1 py-1">{children}</main>
      </div>
    </div>
  );
}
