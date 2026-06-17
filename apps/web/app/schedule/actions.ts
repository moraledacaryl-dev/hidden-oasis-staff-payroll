"use server";

import { cookies } from "next/headers";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function apiHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    "Content-Type": "application/json",
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function moveScheduledShift(shiftId: number, shiftDate: string) {
  if (!shiftId || !shiftDate) return { ok: false, message: "Missing shift or date." };

  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/shifts/${shiftId}/move`, {
    method: "POST",
    headers: await apiHeaders(),
    body: JSON.stringify({ shift_date: shiftDate }),
    cache: "no-store",
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) return { ok: false, message: data.detail || data.message || "Could not move shift." };
  return data;
}
