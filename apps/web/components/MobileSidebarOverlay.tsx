"use client";

import { useEffect } from "react";

export function MobileSidebarOverlay({ className }: { className: string }) {
  useEffect(() => {
    const html = document.documentElement;
    const sidebar = document.getElementById("workspace-navigation");
    const main = document.getElementById("main-content");
    let restore: HTMLElement | null = null;
    let wasOpen = false;
    let previousOverflow = "";
    let focusFrame = 0;
    const close = () => html.removeAttribute("data-sidebar-mobile-open");
    const sync = () => {
      const open = html.hasAttribute("data-sidebar-mobile-open");
      if (open === wasOpen) return;
      wasOpen = open;
      if (open) {
        restore = document.querySelector<HTMLElement>('[aria-controls="workspace-navigation"]');
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        if (main) main.inert = true;
        focusFrame = window.requestAnimationFrame(() => {
          Array.from(document.querySelectorAll<HTMLElement>('#workspace-navigation a[href], #workspace-navigation button:not([disabled])')).find((item) => item.getClientRects().length > 0)?.focus();
        });
      } else {
        if (main) main.inert = false;
        document.body.style.overflow = previousOverflow;
        window.cancelAnimationFrame(focusFrame);
        focusFrame = window.requestAnimationFrame(() => restore?.focus());
      }
    };
    const keydown = (event: KeyboardEvent) => {
      if (!wasOpen || !sidebar) return;
      if (event.key === "Escape") { event.preventDefault(); close(); }
      if (event.key !== "Tab") return;
      const items = Array.from(sidebar.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex="0"]')).filter((item) => item.getClientRects().length);
      const first = items[0], last = items.at(-1);
      if (!first) return;
      if (event.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    };
    const resize = () => { if (window.innerWidth > 920) close(); };
    const observer = new MutationObserver(sync);
    observer.observe(html, { attributes: true, attributeFilter: ["data-sidebar-mobile-open"] });
    document.addEventListener("keydown", keydown); window.addEventListener("resize", resize); sync();
    return () => { close(); sync(); window.cancelAnimationFrame(focusFrame); observer.disconnect(); document.removeEventListener("keydown", keydown); window.removeEventListener("resize", resize); };
  }, []);
  return <button aria-label="Close navigation" className={className} type="button" onClick={() => document.documentElement.removeAttribute("data-sidebar-mobile-open")} />;
}
