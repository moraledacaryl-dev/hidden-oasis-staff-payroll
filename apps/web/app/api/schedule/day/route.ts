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

async function activeLeave(employeeId: number, shiftDate: string) {
  if (!employeeId || !shiftDate) return null;
  const params = new URLSearchParams({ employee_id: String(employeeId), shift_date: shiftDate });
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/day?${params.toString()}`, {
    headers: await apiHeaders(),
    cache: "no-store",
  });
  if (!response.ok) return null;
  const data = await response.json().catch(() => ({}));
  return data.leave || null;
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

  if (section === "reset") {
    const employeeId = Number(body.employee_id || 0);
    const workDate = String(body.work_date || body.shift_date || "");
    if (!employeeId || !workDate) {
      return NextResponse.json({ ok: false, message: "Employee and date are required to clear the day." }, { status: 422 });
    }
    const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/day/reset`, {
      method: "POST",
      headers: await apiHeaders(true),
      body: JSON.stringify({ employee_id: employeeId, work_date: workDate }),
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  }

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

  if (section === "scheduled" || section === "actual") {
    const employeeId = Number(body.employee_id || 0);
    const shiftDate = String(body.shift_date || "");
    const leave = await activeLeave(employeeId, shiftDate);
    if (leave) {
      return NextResponse.json({
        ok: false,
        detail: `This day is marked as ${leave.leave_type_name || "leave"}. Clear the day first before scheduling work or recording actual attendance.`,
      }, { status: 409 });
    }
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
