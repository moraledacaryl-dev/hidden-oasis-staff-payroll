"use client";

import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect } from "react";

let sidebarScrollTop = 0;

function sidebarElement(): HTMLElement | null {
  return document.querySelector<HTMLElement>("[data-sidebar-scroll]");
}

function restoreSidebarScroll() {
  const sidebar = sidebarElement();
  if (sidebar && sidebar.scrollTop !== sidebarScrollTop) {
    sidebar.scrollTop = sidebarScrollTop;
  }
}

export function SidebarScrollMemory() {
  const pathname = usePathname();

  useEffect(() => {
    const rememberScroll = (event: Event) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.hasAttribute("data-sidebar-scroll")) {
        sidebarScrollTop = target.scrollTop;
      }
    };

    let currentSidebar = sidebarElement();
    const observer = new MutationObserver(() => {
      const sidebar = sidebarElement();
      if (sidebar && sidebar !== currentSidebar) {
        currentSidebar = sidebar;
        sidebar.scrollTop = sidebarScrollTop;
      }
    });

    window.addEventListener("scroll", rememberScroll, true);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      window.removeEventListener("scroll", rememberScroll, true);
      observer.disconnect();
    };
  }, []);

  useLayoutEffect(() => {
    restoreSidebarScroll();
    const frame = window.requestAnimationFrame(restoreSidebarScroll);
    return () => window.cancelAnimationFrame(frame);
  }, [pathname]);

  return null;
}
