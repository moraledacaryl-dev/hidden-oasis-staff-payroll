"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

function surfaceIsOpen() {
  return Boolean(document.querySelector(".app-surface-backdrop, .modal-backdrop"));
}

function recoverViewportScroll() {
  if (surfaceIsOpen()) return;

  const html = document.documentElement;
  const body = document.body;

  delete html.dataset.appSurfaceOpen;
  html.style.removeProperty("overflow");
  html.style.removeProperty("overflow-x");
  html.style.removeProperty("overflow-y");
  body.style.removeProperty("overflow");
  body.style.removeProperty("overflow-x");
  body.style.removeProperty("overflow-y");
  body.style.removeProperty("overscroll-behavior");

  // Explicitly restore vertical document scrolling after a drawer or modal has
  // been removed. This protects route transitions where the surface cleanup
  // runs after the destination page has already mounted.
  html.style.overflowX = "hidden";
  html.style.overflowY = "auto";
  body.style.overflowX = "hidden";
  body.style.overflowY = "auto";
}

export function ViewportScrollRecovery() {
  const pathname = usePathname();

  useEffect(() => {
    let frame = 0;
    const scheduleRecovery = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(recoverViewportScroll);
    };

    recoverViewportScroll();
    scheduleRecovery();

    const timers = [50, 150, 350, 700].map((delay) => window.setTimeout(recoverViewportScroll, delay));
    const observer = new MutationObserver(scheduleRecovery);
    observer.observe(document.body, { childList: true, subtree: true });

    window.addEventListener("pageshow", scheduleRecovery);
    window.addEventListener("focus", scheduleRecovery);

    return () => {
      window.cancelAnimationFrame(frame);
      timers.forEach((timer) => window.clearTimeout(timer));
      observer.disconnect();
      window.removeEventListener("pageshow", scheduleRecovery);
      window.removeEventListener("focus", scheduleRecovery);
    };
  }, [pathname]);

  return null;
}
