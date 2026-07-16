"use client";

import { useEffect } from "react";

function findVerticalScroller(start: HTMLElement | null): HTMLElement | Window {
  let current = start?.parentElement || null;
  while (current) {
    const style = window.getComputedStyle(current);
    const overflowY = style.overflowY;
    if ((overflowY === "auto" || overflowY === "scroll") && current.scrollHeight > current.clientHeight) {
      return current;
    }
    current = current.parentElement;
  }
  return window;
}

export function CutoffReviewWheelBridge() {
  useEffect(() => {
    function onWheel(event: WheelEvent) {
      const target = event.target instanceof Element ? event.target.closest(".cutoff-review-card .table-wrap") : null;
      if (!(target instanceof HTMLElement)) return;

      const verticalIntent = Math.abs(event.deltaY) > Math.abs(event.deltaX);
      if (!verticalIntent || event.shiftKey) return;

      const scroller = findVerticalScroller(target);
      event.preventDefault();

      if (scroller === window) {
        window.scrollBy({ top: event.deltaY, left: 0, behavior: "auto" });
      } else {
        scroller.scrollBy({ top: event.deltaY, left: 0, behavior: "auto" });
      }
    }

    document.addEventListener("wheel", onWheel, { passive: false, capture: true });
    return () => document.removeEventListener("wheel", onWheel, { capture: true });
  }, []);

  return null;
}
