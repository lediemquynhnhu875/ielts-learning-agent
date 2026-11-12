import type { ReactNode } from "react";

/** Chữ trong thanh bên: mờ dần khi thu gọn, không đổi bố cục. */
export function Fade({ show, className = "", children }: { show: boolean; className?: string; children: ReactNode }) {
  return (
    <span
      className={`whitespace-nowrap transition-opacity duration-200 motion-reduce:transition-none ${
        show ? "opacity-100 delay-100" : "pointer-events-none opacity-0"
      } ${className}`}
    >
      {children}
    </span>
  );
}
