"use client";

import Link from "next/link";
import { Suspense, useState, useSyncExternalStore } from "react";
import { BookIcon, LoginIcon } from "@/components/icons";
import { roleLabel, type SessionUser } from "@/mock-data/session";
import { visibleNavItems } from "./nav-items";
import { Fade } from "./fade";
import { NavLinks, NavList } from "./nav-list";

type SidebarProps = {
  user: SessionUser | null;
  reportCount: number;
};

const SMALL_SCREEN = "(max-width: 767px)";

function subscribeSmallScreen(onChange: () => void) {
  const query = window.matchMedia(SMALL_SCREEN);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** Màn hình nhỏ: thanh bên mặc định thu gọn để nội dung có chỗ. */
function useSmallScreen() {
  return useSyncExternalStore(
    subscribeSmallScreen,
    () => window.matchMedia(SMALL_SCREEN).matches,
    () => false,
  );
}

export function Sidebar({ user, reportCount }: SidebarProps) {
  const smallScreen = useSmallScreen();
  // null: theo kích thước màn hình; true/false: người dùng đã bấm logo.
  const [manual, setManual] = useState<boolean | null>(null);
  const collapsed = manual ?? smallScreen;
  const setCollapsed = (update: (v: boolean) => boolean) => setManual(update(collapsed));
  const items = visibleNavItems(user);
  const toggleLabel = collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên";

  return (
    <aside
      aria-label="Thanh bên"
      className={[
        "glass-navy sticky top-3 flex h-[calc(100vh-1.5rem)] shrink-0 flex-col gap-[22px] overflow-hidden rounded-[32px] px-3 py-[22px] text-cream md:top-6 md:h-[calc(100vh-3rem)]",
        "transition-[width] duration-300 ease-[cubic-bezier(.2,.8,.2,1)] will-change-[width] motion-reduce:transition-none",
        collapsed ? "w-[80px]" : "w-[232px]",
      ].join(" ")}
    >
      {/* Ánh cam ở chân và ánh xanh ở mép phải, thuần trang trí */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(120px_120px_at_20%_98%,rgb(235_164_94/0.35),transparent),radial-gradient(160px_200px_at_100%_18%,rgb(127_163_224/0.28),transparent),linear-gradient(180deg,rgb(255_255_255/0.1),transparent_22%)]"
      />

      {/* Icon giữ nguyên vị trí khi thu/mở; chữ chỉ mờ dần, không bật tắt đột ngột. */}
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        aria-label={toggleLabel}
        aria-expanded={!collapsed}
        title={toggleLabel}
        className="relative flex cursor-pointer items-center gap-3 rounded-2xl px-2 text-left"
      >
        <span className="grid size-10 shrink-0 place-items-center rounded-[13px] bg-cream text-navy">
          <BookIcon size={21} />
        </span>
        <Fade show={!collapsed} className="text-base font-bold">
          IELTS Agent
        </Fade>
      </button>

      <div className="relative">
        <Suspense fallback={<NavLinks items={items} collapsed={collapsed} reportCount={reportCount} />}>
          <NavList items={items} collapsed={collapsed} reportCount={reportCount} />
        </Suspense>
      </div>

      <div className="relative mt-auto w-full">
        {user ? <UserCard user={user} collapsed={collapsed} /> : <AuthButtons collapsed={collapsed} />}
      </div>
    </aside>
  );
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  const last = parts[parts.length - 1] ?? "";
  const beforeLast = parts[parts.length - 2] ?? "";
  return (beforeLast.charAt(0) + last.charAt(0)).toUpperCase();
}

function UserCard({ user, collapsed }: { user: SessionUser; collapsed: boolean }) {
  return (
    <div
      title={collapsed ? `${user.name}, ${roleLabel[user.role]}` : undefined}
      className={`flex items-center gap-3 rounded-[20px] border p-2 transition-colors duration-300 ${
        collapsed ? "border-transparent bg-transparent" : "border-white/15 bg-white/10"
      }`}
    >
      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-linear-135 from-orange-light to-[#e8963f] font-extrabold text-navy-deep ring-2 ring-cream/60">
        {initials(user.name)}
      </span>
      <Fade show={!collapsed} className="min-w-0 leading-tight">
        <b className="block truncate text-sm">{user.name}</b>
        <span className="text-xs text-cream/70">{roleLabel[user.role]}</span>
      </Fade>
    </div>
  );
}

function AuthButtons({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <Link
        href="/login"
        title={collapsed ? "Đăng nhập" : undefined}
        className="flex h-11 items-center gap-3 rounded-full bg-orange px-[18px] text-sm font-bold text-navy-deep"
      >
        <LoginIcon size={19} className="shrink-0" />
        <Fade show={!collapsed}>Đăng nhập</Fade>
      </Link>
      {!collapsed && (
        <Link
          href="/register"
          className="rounded-full border border-cream/50 py-2.5 text-center text-sm font-semibold text-cream hover:bg-white/10"
        >
          Đăng ký
        </Link>
      )}
    </div>
  );
}
