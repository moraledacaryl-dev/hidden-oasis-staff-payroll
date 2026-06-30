import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import type { ApiMeta, Employee, PayrollPreview } from "./types";

export { apiBaseUrl, backendHeaders };

export type AttendanceException = { id: number; employee_id: number; employee_code: string; full_name: string; department?: string | null; position?: string | null; work_date: string; actual_in: string | null; actual_out: string | null; is_absent: number; attendance_status: string; detected_ot_hours: number; approved_ot_hours: number; ot_status: string; notes?: string | null };
export type AttendanceReview = { id: number; time_log_id: number; reviewer: string; decision: string; reason: string; approved_ot_hours: number; created_at: string; work_date: string; employee_code: string; full_name: string; department?: string | null; position?: string | null };
export type PayrollRun = { id: number; period_start: string; period_end: string; payout_date: string; run_label: string; status: string; prepared_by?: string | null; approved_by?: string | null; approved_at?: string | null; paid_at?: string | null; locked_at?: string | null; reopen_reason?: string | null; validation_summary?: string | null; revision_of_run_id?: number | null; revision_reason?: string | null; revision_treatment?: string | null; superseded_by_run_id?: number | null; created_at: string; totals?: { employees: number; gross_pay: number; net_pay: number; total_deductions: number } };
export type PayrollReviewItem = { id: number; employee_id: number; employee_name: string; employee_code?: string | null; department: string; position?: string | null; gross_pay: number; net_pay: number; total_deductions: number; regular_hours: number; regular_pay: number; approved_ot_hours: number; ot_pay: number; night_diff_hours: number; night_diff_pay: number; holiday_pay: number; paid_leave_pay: number; freelance_pay: number; other_earnings: number; late_minutes: number; undertime_minutes: number; unpaid_absence_days: number; sss_ee: number; philhealth_ee: number; pagibig_ee: number; tax: number; cash_advance_deduction: number; other_deductions: number; warnings?: string | null; leave_summary?: string[] };
export type PayrollRunReview = { ok: boolean; run: PayrollRun; items: PayrollReviewItem[]; mode: string };
export type PayrollCorrection = { id: number; payroll_run_id: number; employee_id: number; employee_name?: string | null; department?: string | null; adjustment_type: "Earning" | "Deduction" | "Note" | string; amount: number; reason: string; apply_to_next_run: number; status?: string | null; applied_to_run_id?: number | null; applied_at?: string | null; voided_by?: string | null; void_reason?: string | null; voided_at?: string | null; created_by?: string | null; created_at?: string | null };
export type PayrollCorrectionsResponse = { ok: boolean; items: PayrollCorrection[]; mode: string };
export type AppUser = { id: number; display_name: string; role: string; role_key: string; active: number; must_change_password: number; mfa_enabled: number; last_login_at?: string | null; created_at?: string | null; employee_id?: number | null; employee_name?: string | null };
export type AppUsersResponse = { ok: boolean; items: AppUser[] };
export type ProductionHealth = {
  ok: boolean;
  checked_by?: string;
  database_path?: string;
  database_exists: boolean;
  backup_dir?: string;
  database_checks: { integrity: string; writable: boolean; migration_version: number };
  backup_count: number;
  latest_backup?: { name: string; created_at: string; encrypted: boolean } | null;
  backup_age_hours?: number | null;
  backup_encryption_configured: boolean;
  offsite_backup_configured: boolean;
  tables?: Record<string, boolean>;
  counts?: Record<string, number>;
  secrets_configured: Record<string, boolean>;
};
export type PayrollRunChange = { id: number; change_type: string; entity_type: string; entity_id?: number | null; employee_id?: number | null; work_date?: string | null; payroll_run_id?: number | null; changed_by?: string | null; changed_at: string; undone_at?: string | null };
export type PayrollRunChangeDelta = { ok: boolean; run_id: number; changed: boolean; change_count: number; changes: PayrollRunChange[] };
export type PayrollQaFlag = { severity: "critical" | "warning" | "info" | string; code: string; label: string; recommended_action: string };
export type PayrollQaSchedule = { id: number; employee_id: number; work_date: string; start_time: string; end_time: string; position?: string | null; department?: string | null; break_minutes?: number | null; notes?: string | null; schedule_source?: string | null };
export type PayrollQaActual = { id: number; employee_id: number; work_date: string; actual_in?: string | null; actual_out?: string | null; source?: string | null; verification_type?: string | null; is_absent?: number | null; absence_type?: string | null; attendance_status?: string | null; approved_ot_hours?: number | null; ot_status?: string | null; notes?: string | null };
export type PayrollQaRow = { employee_id: number; employee_code?: string | null; employee_name: string; department?: string | null; position?: string | null; work_date: string; schedule?: PayrollQaSchedule | null; schedule_count: number; actual?: PayrollQaActual | null; manual_log_count: number; biometric?: PayrollQaActual | null; biometric_log_count: number; approved_leave_count: number; flags: PayrollQaFlag[]; severity: "critical" | "warning" | "info" | string; review_url: string };
export type PayrollQaResponse = { ok: boolean; period_start: string; period_end: string; items: PayrollQaRow[]; totals: { critical: number; warning: number; info: number; rows: number }; mode: string; generated_by?: string | null };

export async function apiHeaders(includeAuth = false): Promise<HeadersInit> {
  return backendHeaders(false, includeAuth);
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

export function getMeta(): Promise<ApiMeta> { return apiGet<ApiMeta>("/api/v1/meta", true); }
export function getEmployees(): Promise<Employee[]> { return apiGet<Employee[]>("/api/v1/staff/employees", true); }
export function getAttendanceExceptions(periodStart: string, periodEnd: string): Promise<AttendanceException[]> { return apiGet<AttendanceException[]>(`/api/v1/attendance/exceptions?start_date=${periodStart}&end_date=${periodEnd}`, true); }
export function getAttendanceReviews(periodStart: string, periodEnd: string): Promise<AttendanceReview[]> { return apiGet<AttendanceReview[]>(`/api/v1/attendance/reviews?start_date=${periodStart}&end_date=${periodEnd}`, true); }
export function getPayrollRuns(): Promise<PayrollRun[]> { return apiGet<PayrollRun[]>("/api/v1/payroll/runs", true); }
export function getPayrollRunReview(runId: number): Promise<PayrollRunReview> { return apiGet<PayrollRunReview>(`/api/v1/payroll/runs/${runId}/review`, true); }
export function getPayrollRunChangeDelta(runId: number): Promise<PayrollRunChangeDelta> { return apiGet<PayrollRunChangeDelta>(`/api/v1/payroll/runs/${runId}/change-delta`, true); }
export function getPayrollCorrections(runId: number): Promise<PayrollCorrectionsResponse> { return apiGet<PayrollCorrectionsResponse>(`/api/v1/payroll/runs/${runId}/corrections`, true); }
export function getAppUsers(): Promise<AppUsersResponse> { return apiGet<AppUsersResponse>("/api/v1/users", true); }
export function getProductionHealth(): Promise<ProductionHealth> { return apiGet<ProductionHealth>("/api/v1/production/health", true); }
export function getPayrollPreview(periodStart: string, periodEnd: string): Promise<PayrollPreview> { return apiPost<PayrollPreview>("/api/v1/payroll/preview", { period_start: periodStart, period_end: periodEnd }, true); }
export function getPayrollQa(periodStart: string, periodEnd: string, includeInfo = false): Promise<PayrollQaResponse> { return apiGet<PayrollQaResponse>(`/api/v1/payroll/qa?period_start=${periodStart}&period_end=${periodEnd}&include_info=${includeInfo ? "true" : "false"}`, true); }
export function peso(value: number | null | undefined): string { return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP", maximumFractionDigits: 2 }).format(Number(value || 0)); }
export function numberText(value: number | null | undefined, digits = 2): string { return Number(value || 0).toLocaleString("en-PH", { minimumFractionDigits: digits, maximumFractionDigits: digits }); }
