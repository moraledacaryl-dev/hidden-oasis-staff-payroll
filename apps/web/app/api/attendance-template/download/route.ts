import { NextRequest } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { addIsoDays, mondayOfWeek } from "@/lib/period";
import { currentSession } from "@/lib/session";
import type { ScheduleEmployee } from "@/lib/schedule-types";

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

function csvCell(value: string | number | null | undefined) {
  const text = String(value ?? "");
  if (!/[",\n]/.test(text)) return text;
  return `"${text.replaceAll('"', '""')}"`;
}

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
  if (!session || session.role_key !== "owner") {
    return Response.json({ message: "Only the owner can download attendance templates." }, { status: 403 });
  }
  const params = request.nextUrl.searchParams;
  const start = validIsoDate(params.get("start")) ? params.get("start")! : mondayOfWeek();
  const days = Math.min(31, Math.max(1, Number(params.get("days") || 7) || 7));
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
    },
  });
}
