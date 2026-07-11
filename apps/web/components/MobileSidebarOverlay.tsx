"use client";

export function MobileSidebarOverlay({ className }: { className: string }) {
  return (
    <button
      aria-label="Close navigation"
      className={className}
      type="button"
      onClick={() => document.documentElement.removeAttribute("data-sidebar-mobile-open")}
    />
  );
}
