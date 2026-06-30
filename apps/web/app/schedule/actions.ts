"use server";

import { apiBaseUrl } from "@/lib/backend";
import { backendHeaders } from "@/lib/backend";

async function changeScheduledShift(
  operation: "move" | "duplicate",
  shiftId: number,
  shiftDate: string,
  employeeId: number | null,
) {
  if (!shiftId || !shiftDate) return { ok: false, message: "Missing shift or date." };

  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/shifts/${shiftId}/${operation}`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({ shift_date: shiftDate, employee_id: employeeId }),
    cache: "no-store",
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) return { ok: false, message: data.detail || data.message || `Could not ${operation === "move" ? "move" : "copy"} shift.` };
  return data;
}

export async function moveScheduledShift(shiftId: number, shiftDate: string, employeeId: number | null) {
  return changeScheduledShift("move", shiftId, shiftDate, employeeId);
}

export async function copyScheduledShift(shiftId: number, shiftDate: string, employeeId: number | null) {
  return changeScheduledShift("duplicate", shiftId, shiftDate, employeeId);
}
