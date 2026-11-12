import type { ComponentType, SVGProps } from "react";
import type { Role, SessionUser } from "@/mock-data/session";
import { ChartIcon, ClockIcon, FlagIcon, GridIcon, HomeIcon, SettingsIcon } from "@/components/icons";

export type NavItem = {
  href: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;
  /** Chỉ hiện với các vai trò này; bỏ trống là hiện cho mọi người. */
  roles?: Role[];
  /** Hiện badge số câu bị báo sai. */
  showReportBadge?: boolean;
};

export const navItems: NavItem[] = [
  { href: "/", label: "Trang chủ", icon: HomeIcon },
  { href: "/exercises", label: "Kho đề", icon: GridIcon },
  { href: "/mock", label: "Thi thử", icon: ClockIcon, roles: ["learner"] },
  { href: "/reports", label: "Câu bị báo sai", icon: FlagIcon, roles: ["teacher"], showReportBadge: true },
  { href: "/stats", label: "Thống kê", icon: ChartIcon },
  { href: "/settings", label: "Cài đặt", icon: SettingsIcon },
];

/** Mục thanh bên theo vai trò; chưa đăng nhập chỉ thấy mục không giới hạn vai trò. */
export function visibleNavItems(user: SessionUser | null): NavItem[] {
  return navItems.filter((item) => !item.roles || (user !== null && item.roles.includes(user.role)));
}

export function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
