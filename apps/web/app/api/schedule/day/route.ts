import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

function normalized(value: unknown): string {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function isSil(value: unknown): boolean {
  return [
    "sil",
    "service incentive leave",
    "service incentive leave (sil)",
    "sil (service incentive leave)",
  ].includes(normalized(value));
}

async function activeLeave(employeeId: number, shiftDate: string) {
  if (!employeeId || !shiftDate) return null;
  const params = new URLSearchParams({ employee_id: String(employeeId), shift_date: shiftDate });
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/day?${params.toString()}`, {
    headers: await backendHeaders(),
    cache: "no-store",
  });
  if (!response.ok) return null;
  const data = await response.json().catch(() => ({}));
  return data.leave || null;
}

async function clearRestDay(employeeId: number, workDate: string) {
  if (!employeeId || !workDate) return;
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/rest-days`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({ employee_id: employeeId, work_date: workDate, active: false }),
    cache: "no-store",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : data.message || "Could not clear rest day.");
  }
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/day?${url.searchParams.toString()}`, {
    headers: await backendHeaders(),
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
    const clearReason = String(body.clear_reason || "").trim();
    const confirmation = String(body.confirmation || "").trim();
    if (!employeeId || !workDate) {
      return NextResponse.json({ ok: false, message: "Employee and date are required to clear the day." }, { status: 422 });
    }
    if (clearReason.length < 10) {
      return NextResponse.json({ ok: false, message: "Clear Day reason must be at least 10 characters." }, { status: 422 });
    }
    if (confirmation !== "CLEAR DAY") {
      return NextResponse.json({ ok: false, message: "Type CLEAR DAY to confirm clearing this employee day." }, { status: 422 });
    }
    const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/day/reset`, {
      method: "POST",
      headers: await backendHeaders(true),
      body: JSON.stringify({ employee_id: employeeId, work_date: workDate, clear_reason: clearReason, confirmation }),
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
      headers: await backendHeaders(),
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

    try {
      await clearRestDay(employeeId, shiftDate);
    } catch (error) {
      return NextResponse.json({
        ok: false,
        detail: error instanceof Error ? error.message : "Could not clear rest day.",
      }, { status: 409 });
    }
  }

  let route = section === "scheduled" || section === "actual" || section === "leave" ? section : "";
  if (section === "leave" && isSil(body.leave_kind)) {
    route = "sil";
    body.leave_kind = "SIL";
  }
  if (!route) return NextResponse.json({ ok: false, message: "Invalid schedule day section." }, { status: 422 });

  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/day/${route}`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
