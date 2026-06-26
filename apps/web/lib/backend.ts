import { cookies } from "next/headers";
import { ACCESS_TOKEN_COOKIE } from "./session-client";

export function apiBaseUrl(): string {
  return (
    process.env.STAFF_PAYROLL_API_URL ||
    process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL ||
    "http://127.0.0.1:8001"
  ).replace(/\/$/, "");
}

export async function backendHeaders(
  json = false,
  includeAuth = true,
): Promise<Record<string, string>> {
  const token = includeAuth
    ? (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value
    : undefined;
  return {
    Accept: "application/json",
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY
      ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY }
      : {}),
  };
}
