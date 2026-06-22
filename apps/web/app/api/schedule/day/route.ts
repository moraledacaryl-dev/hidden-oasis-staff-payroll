import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function apiHeaders(json = false): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

function normalized(value: unknown): string {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function isApprovedLeave(value: unknown): boolean {
  return [
    "none",
    "sil",
    "service incentive leave",
    "service incentive leave (sil)",
    "sil (service incentive leave)",
    "sick leave",
    "vacation leave",
    "emergency leave",
    "bereavement leave",
    "official business",
    "other approved absence",
  ].includes(normalized(value));
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/day?${url.searchParams.toString()}`, {
    headers: await apiHeaders(),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: Request) {
  const body = await request.json();
  const section = String(body.section || "");
  if (section === "remove") {
    const shiftId = Number(body.shift_id || 0);
    if (!shiftId) return NextResponse.json({ ok: false, message: "Missing schedule shift." }, { status: 422 });
    const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/shifts/${shiftId}/delete`, {
      method: "POST",
      headers: await apiHeaders(),
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  }

  let route = section === "scheduled" || section === "actual" || section === "leave" ? section : "";
  if (section === "leave" && isApprovedLeave(body.leave_kind)) {
    route = "approved-leave";
    if (["service incentive leave", "service incentive leave (sil)", "sil (service incentive leave)"].includes(normalized(body.leave_kind))) {
      body.leave_kind = "SIL";
    }
  }
  if (!route) return NextResponse.json({ ok: false, message: "Invalid schedule day section." }, { status: 422 });

  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/day/${route}`, {
    method: "POST",
    headers: await apiHeaders(true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
