import { cookies } from "next/headers";
import { ACCESS_TOKEN_COOKIE } from "./session-client";
import type { ApiMeta, Employee, PayrollPreview } from "./types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8001";

export type AttendanceException = { id: number; employee_id: number; employee_code: string; full_name: string; department?: string | null; position?: string | null; work_date: string; actual_in: string | null; actual_out: string | null; is_absent: number; attendance_status: string; detected_ot_hours: number; approved_ot_hours: number; ot_status: string; notes?: string | null };
export type AttendanceReview = { id: number; time_log_id: number; reviewer: string; decision: string; reason: string; approved_ot_hours: number; created_at: string; work_date: string; employee_code: string; full_name: string; department?: string | null; position?: string | null };
export type PayrollRun = { id: number; period_start: string; period_end: string; payout_date: string; run_label: string; status: string; prepared_by?: string | null; approved_by?: string | null; approved_at?: string | null; paid_at?: string | null; locked_at?: string | null; validation_summary?: string | null; created_at: string; totals?: { employees: number; gross_pay: number; net_pay: number; total_deductions: number } };
export type PayrollReviewItem = { id: number; employee_id: number; employee_name: string; department: string; gross_pay: number; net_pay: number; total_deductions: number; regular_hours: number; regular_pay: number; approved_ot_hours: number; ot_pay: number; night_diff_pay: number; holiday_pay: number; paid_leave_pay: number; freelance_pay: number; other_earnings: number; late_minutes: number; undertime_minutes: number; unpaid_absence_days: number; sss_ee: number; philhealth_ee: number; pagibig_ee: number; tax: number; cash_advance_deduction: number; other_deductions: number; warnings?: string | null; leave_summary?: string[] };
export type PayrollRunReview = { ok: boolean; run: PayrollRun; items: PayrollReviewItem[]; mode: string };

export function apiBaseUrl(): string { return (process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || DEFAULT_API_BASE_URL).replace(/\/$/, ""); }

async function apiHeaders(includeAuth = false): Promise<HeadersInit> {
  const headers: HeadersInit = { Accept: "application/json" };
  const key = process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_KEY || process.env.STAFF_PAYROLL_API_KEY;
  if (key) headers["X-API-Key"] = key;
  if (includeAuth) { const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value; if (token) headers.Authorization = `Bearer ${token}`; }
  return headers;
}

async function apiGet<T>(path: string, includeAuth = false): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, { method: "GET", headers: await apiHeaders(includeAuth), cache: "no-store" });
  if (!response.ok) throw new Error(`API GET ${path} failed: ${response.status} ${await response.text()}`);
  return response.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown, includeAuth = false): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, { method: "POST", headers: { ...(await apiHeaders(includeAuth)), "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
  if (!response.ok) throw new Error(`API POST ${path} failed: ${response.status} ${await response.text()}`);
  return response.json() as Promise<T>;
}

export function getMeta(): Promise<ApiMeta> { return apiGet<ApiMeta>("/api/v1/meta"); }
export function getEmployees(): Promise<Employee[]> { return apiGet<Employee[]>("/api/v1/staff/employees"); }
export function getAttendanceExceptions(periodStart: string, periodEnd: string): Promise<AttendanceException[]> { return apiGet<AttendanceException[]>(`/api/v1/attendance/exceptions?start_date=${periodStart}&end_date=${periodEnd}`, true); }
export function getAttendanceReviews(periodStart: string, periodEnd: string): Promise<AttendanceReview[]> { return apiGet<AttendanceReview[]>(`/api/v1/attendance/reviews?start_date=${periodStart}&end_date=${periodEnd}`, true); }
export function getPayrollRuns(): Promise<PayrollRun[]> { return apiGet<PayrollRun[]>("/api/v1/payroll/runs", true); }
export function getPayrollRunReview(runId: number): Promise<PayrollRunReview> { return apiGet<PayrollRunReview>(`/api/v1/payroll/runs/${runId}/review`, true); }
export function getPayrollPreview(periodStart: string, periodEnd: string): Promise<PayrollPreview> { return apiPost<PayrollPreview>("/api/v1/payroll/preview", { period_start: periodStart, period_end: periodEnd }); }
export function peso(value: number | null | undefined): string { return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP", maximumFractionDigits: 2 }).format(Number(value || 0)); }
export function numberText(value: number | null | undefined, digits = 2): string { return Number(value || 0).toLocaleString("en-PH", { minimumFractionDigits: digits, maximumFractionDigits: digits }); }
