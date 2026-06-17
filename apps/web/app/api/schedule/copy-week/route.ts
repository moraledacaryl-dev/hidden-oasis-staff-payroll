import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { cookies } from "next/headers";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function apiHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    "Content-Type": "application/json",
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function POST(request: Request) {
  const body = await request.json();
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/copy-week`, {
    method: "POST",
    headers: await apiHeaders(),
    body: JSON.stringify({ from_week_start: body.from_week_start, to_week_start: body.to_week_start }),
    cache: "no-store",
  });

  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
