"use client";

import { useEffect } from "react";

function findVerticalScroller(start: HTMLElement | null): HTMLElement {
  let current = start?.parentElement || null;
  while (current) {
    const style = window.getComputedStyle(current);
    const overflowY = style.overflowY;
    if ((overflowY === "auto" || overflowY === "scroll") && current.scrollHeight > current.clientHeight) {
      return current;
    }
    current = current.parentElement;
  }

  return (document.scrollingElement as HTMLElement | null) || document.documentElement;
}

function pixelDelta(event: WheelEvent): number {
  if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) return event.deltaY * 16;
  if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) return event.deltaY * window.innerHeight;
  return event.deltaY;
}

export function CutoffReviewWheelBridge() {
  useEffect(() => {
    function onWheel(event: WheelEvent) {
      const target = event.target instanceof Element ? event.target.closest(".cutoff-review-card .table-wrap") : null;
      if (!(target instanceof HTMLElement)) return;

      const verticalIntent = Math.abs(event.deltaY) >= Math.abs(event.deltaX);
      if (!verticalIntent || event.shiftKey) return;

      const scroller = findVerticalScroller(target);
      const delta = pixelDelta(event);
      if (!delta) return;

      event.preventDefault();
      scroller.scrollTop += delta;
    }

    document.addEventListener("wheel", onWheel, { passive: false, capture: true });
    return () => document.removeEventListener("wheel", onWheel, { capture: true });
  }, []);

  return null;
}
