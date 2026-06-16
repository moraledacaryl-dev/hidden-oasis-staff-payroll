import { cookies } from "next/headers";
import { ACCESS_TOKEN_COOKIE } from "./session-client";
import type { ApiMeta, Employee, PayrollPreview } from "./types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8001";

export type AttendanceException = {
  id: number;
  employee_id: number;
  employee_code: string;
  full_name: string;
  department?: string | null;
  position?: string | null;
  work_date: string;
  actual_in: string | null;
  actual_out: string | null;
  is_absent: number;
  attendance_status: string;
  detected_ot_hours: number;
  approved_ot_hours: number;
  ot_status: string;
  notes?: string | null;
};

export function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || DEFAULT_API_BASE_URL).replace(/\/$/, "");
}

async function apiHeaders(includeAuth = false): Promise<HeadersInit> {
  const headers: HeadersInit = { Accept: "application/json" };
  const key = process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_KEY || process.env.STAFF_PAYROLL_API_KEY;
  if (key) headers["X-API-Key"] = key;
  if (includeAuth) {
    const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function apiGet<T>(path: string, includeAuth = false): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, { method: "GET", headers: await apiHeaders(includeAuth), cache: "no-store" });
  if (!response.ok) throw new Error(`API GET ${path} failed: ${response.status} ${await response.text()}`);
  return response.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown, includeAuth = false): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method: "POST",
    headers: { ...(await apiHeaders(includeAuth)), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`API POST ${path} failed: ${response.status} ${await response.text()}`);
  return response.json() as Promise<T>;
}

export function getMeta(): Promise<ApiMeta> {
  return apiGet<ApiMeta>("/api/v1/meta");
}

export function getEmployees(): Promise<Employee[]> {
  return apiGet<Employee[]>("/api/v1/staff/employees");
}

export function getAttendanceExceptions(periodStart: string, periodEnd: string): Promise<AttendanceException[]> {
  return apiGet<AttendanceException[]>(`/api/v1/attendance/exceptions?start_date=${periodStart}&end_date=${periodEnd}`, true);
}

export function getPayrollPreview(periodStart: string, periodEnd: string): Promise<PayrollPreview> {
  return apiPost<PayrollPreview>("/api/v1/payroll/preview", { period_start: periodStart, period_end: periodEnd });
}

export function peso(value: number | null | undefined): string {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP", maximumFractionDigits: 2 }).format(amount);
}

export function numberText(value: number | null | undefined, digits = 2): string {
  return Number(value || 0).toLocaleString("en-PH", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
