"use server";

import { apiBaseUrl } from "@/lib/backend";
import { backendHeaders } from "@/lib/backend";

export async function moveScheduledShift(shiftId: number, shiftDate: string) {
  if (!shiftId || !shiftDate) return { ok: false, message: "Missing shift or date." };

  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/shifts/${shiftId}/move`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({ shift_date: shiftDate }),
    cache: "no-store",
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) return { ok: false, message: data.detail || data.message || "Could not move shift." };
  return data;
}
