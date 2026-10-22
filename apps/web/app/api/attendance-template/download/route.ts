import { NextRequest } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { addIsoDays, mondayOfWeek } from "@/lib/period";
import type { ScheduleEmployee } from "@/lib/schedule-types";
import { csvCell } from "@/lib/csv-security.mjs";
import { currentSession } from "@/lib/session";

const COLUMNS = [
  "work_date",
  "employee_name",
  "biometric_id",
  "time_in",
  "time_out",
  "time_out_date",
  "break_minutes",
  "attendance_status",
  "remarks",
  "is_absent",
  "is_halfday",
  "is_ot",
  "ot_hours",
  "ot_reason",
  "needs_review",
  "review_note",
];

function validIsoDate(value: string | null) {
  return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value));
}

async function loadEmployees(): Promise<ScheduleEmployee[]> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/employees`, {
    headers: await backendHeaders(),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Employees could not be loaded (${response.status}).`);
  const data = await response.json();
  return (data.items || []).sort((a: ScheduleEmployee, b: ScheduleEmployee) => a.full_name.localeCompare(b.full_name));
}

export async function GET(request: NextRequest) {
  const session = await currentSession();
  if (!session) return new Response("Authentication required.", { status: 401, headers: { "Cache-Control": "no-store" } });
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) {
    return new Response("Attendance export access denied.", { status: 403, headers: { "Cache-Control": "no-store" } });
  }

  const params = request.nextUrl.searchParams;
  const suppliedStart = params.get("start");
  if (suppliedStart !== null && !validIsoDate(suppliedStart)) {
    return new Response("Invalid start date.", { status: 400 });
  }
  const start = suppliedStart ?? mondayOfWeek();
  const requestedDays = params.get("days");
  const days = requestedDays === null ? 7 : Number(requestedDays);
  if (!Number.isSafeInteger(days) || days < 1 || days > 31) {
    return new Response("Days must be an integer from 1 to 31.", { status: 400 });
  }
  const employees = await loadEmployees();
  const dates = Array.from({ length: days }, (_, index) => addIsoDays(start, index));

  const rows = [COLUMNS.join(",")];
  for (const workDate of dates) {
    for (const employee of employees) {
      rows.push([
        workDate,
        employee.full_name,
        employee.employee_code || "",
        "",
        "",
        workDate,
        employee.unpaid_break_minutes ?? 60,
        "",
        "",
        0,
        0,
        0,
        "",
        "",
        0,
        "",
      ].map(csvCell).join(","));
    }
  }

  const fileName = `attendance-template-${start}-${days}d.csv`;
  return new Response(`${rows.join("\n")}\n`, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename=${fileName}`,
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
