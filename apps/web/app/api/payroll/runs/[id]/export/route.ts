import { NextResponse } from "next/server";
import { getPayrollCorrections, getPayrollRunReview } from "@/lib/api";

function csvCell(value: unknown): string {
  const text = value == null ? "" : String(value);
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function toCsv(headers: string[], rows: unknown[][]): string {
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n") + "\n";
}

function download(csv: string, filename: string) {
  return new NextResponse(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-store",
    },
  });
}

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const runId = Number(id);
  const type = new URL(request.url).searchParams.get("type") || "items";
  const review = await getPayrollRunReview(runId);
  const run = review.run;

  if (type === "corrections") {
    const corrections = await getPayrollCorrections(runId);
    const csv = toCsv(
      ["created_at", "employee", "type", "status", "amount", "apply_to_next_run", "applied_to_run_id", "reason", "created_by"],
      corrections.items.map((item) => [
        item.created_at || "",
        item.employee_name || `Employee ${item.employee_id}`,
        item.adjustment_type,
        item.status || "Recorded",
        item.adjustment_type === "Note" ? "" : item.amount,
        item.apply_to_next_run ? "Yes" : "No",
        item.applied_to_run_id || "",
        item.reason,
        item.created_by || "",
      ]),
    );
    return download(csv, `payroll-run-${run.id}-corrections.csv`);
  }

  if (type === "summary") {
    const byDepartment = new Map<string, { employees: number; gross: number; deductions: number; net: number }>();
    for (const item of review.items) {
      const key = item.department || "Unassigned";
      const current = byDepartment.get(key) || { employees: 0, gross: 0, deductions: 0, net: 0 };
      current.employees += 1;
      current.gross += Number(item.gross_pay || 0);
      current.deductions += Number(item.total_deductions || 0);
      current.net += Number(item.net_pay || 0);
      byDepartment.set(key, current);
    }
    const csv = toCsv(
      ["department", "employees", "gross_pay", "deductions", "net_pay"],
      Array.from(byDepartment.entries()).map(([department, total]) => [department, total.employees, total.gross.toFixed(2), total.deductions.toFixed(2), total.net.toFixed(2)]),
    );
    return download(csv, `payroll-run-${run.id}-department-summary.csv`);
  }

  const csv = toCsv(
    [
      "employee", "department", "regular_hours", "regular_pay", "ot_hours", "ot_pay", "night_diff_pay", "holiday_pay", "paid_leave_pay", "other_earnings", "gross_pay", "sss", "philhealth", "pagibig", "tax", "cash_advance", "other_deductions", "total_deductions", "net_pay", "warnings",
    ],
    review.items.map((item) => [
      item.employee_name,
      item.department,
      item.regular_hours,
      item.regular_pay,
      item.approved_ot_hours,
      item.ot_pay,
      item.night_diff_pay,
      item.holiday_pay,
      item.paid_leave_pay,
      item.other_earnings,
      item.gross_pay,
      item.sss_ee,
      item.philhealth_ee,
      item.pagibig_ee,
      item.tax,
      item.cash_advance_deduction,
      item.other_deductions,
      item.total_deductions,
      item.net_pay,
      item.warnings || "",
    ]),
  );
  return download(csv, `payroll-run-${run.id}-items.csv`);
}
