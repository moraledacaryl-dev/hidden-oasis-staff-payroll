"use client";

import { useEffect } from "react";

export function ScheduleAddShiftBridge() {
  useEffect(() => {
    function handleClick(event: MouseEvent) {
      const target = event.target as Element | null;
      const link = target?.closest('a[href="#schedule-grid"]');
      if (!link) return;
      event.preventDefault();
      window.dispatchEvent(new Event("schedule:add-shift"));
    }
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);
  return null;
}
