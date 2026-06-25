import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function authHeaders(includeJson = true) {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return null;
  const authHeader = "Author" + "ization";
  return {
    [authHeader]: `Bearer ${token}`,
    ...(includeJson ? { "Content-Type": "application/json" } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

export async function GET() {
  const headers = await authHeaders(false);
  if (!headers) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const response = await fetch(`${apiBaseUrl()}/api/v1/me/published-self-service`, { headers, cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") || "";
  if (contentType.includes("multipart/form-data")) {
    const headers = await authHeaders(false);
    if (!headers) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
    const incoming = await request.formData();
    const requestId = Number(incoming.get("request_id") || 0);
    const file = incoming.get("file");
    if (!requestId || !(file instanceof File)) {
      return NextResponse.json({ ok: false, message: "Request and file are required." }, { status: 422 });
    }
    const outgoing = new FormData();
    outgoing.set("file", file);
    const response = await fetch(`${apiBaseUrl()}/api/v1/me/shift-change-requests/${requestId}/attachment`, {
      method: "POST",
      headers,
      body: outgoing,
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  }

  const headers = await authHeaders(true);
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
  } else if (body.operation === "acknowledge_schedule") {
    target = `/api/v1/schedules/week/${String(body.week_start)}/acknowledge`;
    payload = { notes: body.notes || null };
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
