"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

function recoverViewportScroll() {
  if (document.querySelector(".app-surface-backdrop")) return;

  const html = document.documentElement;
  const body = document.body;
  delete html.dataset.appSurfaceOpen;
  html.style.removeProperty("overflow");
  html.style.removeProperty("overflow-x");
  body.style.removeProperty("overflow");
  body.style.removeProperty("overflow-x");
  body.style.removeProperty("overscroll-behavior");
}

export function ViewportScrollRecovery() {
  const pathname = usePathname();

  useEffect(() => {
    recoverViewportScroll();
    const frame = window.requestAnimationFrame(recoverViewportScroll);
    const timer = window.setTimeout(recoverViewportScroll, 120);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [pathname]);

  return null;
}
