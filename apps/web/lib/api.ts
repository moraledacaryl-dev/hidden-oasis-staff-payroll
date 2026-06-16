import type { ApiMeta, Employee, PayrollPreview } from "./types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8001";

export function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || DEFAULT_API_BASE_URL).replace(/\/$/, "");
}

function apiHeaders(): HeadersInit {
  const headers: HeadersInit = {
    Accept: "application/json",
  };
  const key = process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_KEY;
  if (key) {
    headers["X-API-Key"] = key;
  }
  return headers;
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method: "GET",
    headers: apiHeaders(),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API GET ${path} failed: ${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method: "POST",
    headers: {
      ...apiHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API POST ${path} failed: ${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export function getMeta(): Promise<ApiMeta> {
  return apiGet<ApiMeta>("/api/v1/meta");
}

export function getEmployees(): Promise<Employee[]> {
  return apiGet<Employee[]>("/api/v1/staff/employees");
}

export function getPayrollPreview(periodStart: string, periodEnd: string): Promise<PayrollPreview> {
  return apiPost<PayrollPreview>("/api/v1/payroll/preview", {
    period_start: periodStart,
    period_end: periodEnd,
  });
}

export function peso(value: number | null | undefined): string {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    maximumFractionDigits: 2,
  }).format(amount);
}

export function numberText(value: number | null | undefined, digits = 2): string {
  return Number(value || 0).toLocaleString("en-PH", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
