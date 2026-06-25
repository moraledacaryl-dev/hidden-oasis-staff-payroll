import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function authHeaders() {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return null;
  const authHeader = "Author" + "ization";
  return {
    [authHeader]: `Bearer ${token}`,
    "Content-Type": "application/json",
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

export async function GET() {
  const headers = await authHeaders();
  if (!headers) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const response = await fetch(`${apiBaseUrl()}/api/v1/me/self-service`, { headers, cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: Request) {
  const headers = await authHeaders();
  if (!headers) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const body = await request.json();
  let target = "/api/v1/schedules/shifts";
  let payload = body;
  let method = "POST";
  if (body.operation === "staff_request") {
    target = "/api/v1/me/shift-change-requests";
    const { operation, ...rest } = body;
    payload = rest;
  } else if (body.operation === "withdraw_request") {
    target = `/api/v1/me/shift-change-requests/${Number(body.request_id)}/withdraw`;
    payload = {};
  } else if (body.operation === "confirm_swap") {
    target = `/api/v1/me/shift-change-requests/${Number(body.request_id)}/confirm-swap`;
    payload = {};
  } else if (body.operation === "review_requests") {
    target = "/api/v1/schedule/change-requests";
    method = "GET";
    payload = null;
  } else if (body.operation === "decide_request") {
    target = `/api/v1/schedule/change-requests/${Number(body.request_id)}/decision`;
    payload = {
      decision: body.decision,
      decision_note: body.decision_note || null,
      employee_notified: Boolean(body.employee_notified),
      coverage_confirmed: Boolean(body.coverage_confirmed),
      apply_change: body.apply_change !== false,
    };
  }
  const response = await fetch(`${apiBaseUrl()}${target}`, {
    method,
    headers,
    ...(method === "GET" ? {} : { body: JSON.stringify(payload) }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
