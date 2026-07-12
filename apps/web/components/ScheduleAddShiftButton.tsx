"use client";

export function ScheduleAddShiftButton() {
  return <button className="button" type="button" onClick={() => window.dispatchEvent(new Event("schedule:add-shift"))}>+ Add shift</button>;
}
