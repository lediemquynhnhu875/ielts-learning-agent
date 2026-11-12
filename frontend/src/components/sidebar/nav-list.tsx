"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { NavItem } from "./nav-items";
import { isActive } from "./nav-items";
import { Fade } from "./fade";

type NavListProps = {
  items: NavItem[];
  collapsed: boolean;
  reportCount: number;
  /** Bỏ qua usePathname, dùng làm fallback của Suspense khi đường dẫn chưa biết lúc prerender. */
  pathname?: string | null;
};

export function NavList(props: Omit<NavListProps, "pathname">) {
  const pathname = usePathname();
  return <NavLinks {...props} pathname={pathname} />;
}

export function NavLinks({ items, collapsed, reportCount, pathname }: NavListProps) {
  return (
    <nav aria-label="Điều hướng chính" className="flex flex-col gap-1.5">
      {items.map((item) => {
        const active = pathname ? isActive(pathname, item.href) : false;
        const Icon = item.icon;
        const badge = item.showReportBadge && reportCount > 0;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            title={collapsed ? item.label : undefined}
            className={[
              "relative flex h-11 items-center gap-3 rounded-[16px] px-[18px] text-sm transition-colors",
              active
                ? "bg-orange font-bold text-navy-deep shadow-[0_8px_20px_rgb(235_164_94/0.4),inset_0_1px_0_rgb(255_255_255/0.5)]"
                : "font-medium text-cream/80 hover:bg-white/10 hover:text-cream",
            ].join(" ")}
          >
            <Icon size={19} className="shrink-0" />
            <Fade show={!collapsed} className="flex-1">
              {item.label}
            </Fade>
            {badge && (
              <>
                <span
                  aria-label={`${reportCount} câu chờ xử lý`}
                  className={`grid h-5 min-w-5 place-items-center rounded-full bg-orange px-1.5 text-[11px] font-bold text-navy-deep transition-opacity duration-200 ${
                    collapsed ? "opacity-0" : "opacity-100 delay-100"
                  }`}
                >
                  {reportCount}
                </span>
                <span
                  aria-hidden="true"
                  className={`absolute left-[33px] top-2 size-2.5 rounded-full bg-orange ring-2 ring-navy transition-opacity duration-200 ${
                    collapsed ? "opacity-100 delay-100" : "opacity-0"
                  }`}
                />
              </>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
