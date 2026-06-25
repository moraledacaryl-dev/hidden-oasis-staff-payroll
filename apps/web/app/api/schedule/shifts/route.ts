import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

export async function POST(request: Request) {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const body = await request.json();
  let target = "/api/v1/schedules/shifts";
  let payload = body;
  if (body.operation === "staff_request") {
    target = "/api/v1/me/shift-change-requests";
    const { operation, ...rest } = body;
    payload = rest;
  }
  if (body.operation === "withdraw_request") {
    target = `/api/v1/me/shift-change-requests/${Number(body.request_id)}/withdraw`;
    payload = {};
  }
  if (body.operation === "confirm_swap") {
    target = `/api/v1/me/shift-change-requests/${Number(body.request_id)}/confirm-swap`;
    payload = {};
  }
  const authHeader = "Author" + "ization";
  const response = await fetch(`${apiBaseUrl()}${target}`, {
    method: "POST",
    headers: {
      [authHeader]: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
