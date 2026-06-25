import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

const base = () => (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");

async function headers(json = false) {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return null;
  const auth = "Author" + "ization";
  return {
    [auth]: `Bearer ${token}`,
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

export async function GET() {
  const h = await headers();
  if (!h) return NextResponse.json({ ok: false }, { status: 401 });
  const response = await fetch(`${base()}/api/v1/me/published-self-service`, { headers: h, cache: "no-store" });
  return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
}

export async function POST(request: Request) {
  const multipart = (request.headers.get("content-type") || "").includes("multipart/form-data");
  const h = await headers(!multipart);
  if (!h) return NextResponse.json({ ok: false }, { status: 401 });

  if (multipart) {
    const incoming = await request.formData();
    const id = Number(incoming.get("request_id") || 0);
    const file = incoming.get("file");
    if (!id || !(file instanceof File)) return NextResponse.json({ ok: false, message: "Request and file are required." }, { status: 422 });
    const outgoing = new FormData();
    outgoing.set("file", file);
    const response = await fetch(`${base()}/api/v1/me/shift-change-requests/${id}/attachment`, { method: "POST", headers: h, body: outgoing, cache: "no-store" });
    return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
  }

  const body = await request.json();
  let path = "/api/v1/schedules/shifts";
  let payload: unknown = body;
  let method = "POST";

  if (body.operation === "staff_request") {
    path = "/api/v1/me/shift-change-requests";
    const { operation, ...rest } = body;
    payload = rest;
  } else if (body.operation === "withdraw_request") {
    path = `/api/v1/me/shift-change-requests/${Number(body.request_id)}/withdraw`;
    payload = {};
  } else if (body.operation === "confirm_swap") {
    path = `/api/v1/me/shift-change-requests/${Number(body.request_id)}/confirm-swap`;
    payload = {};
  } else if (body.operation === "acknowledge_schedule") {
    path = `/api/v1/me/schedules/week/${String(body.week_start)}/acknowledge`;
    payload = { notes: body.notes || null };
  } else if (body.operation === "get_schedule_publication") {
    path = `/api/v1/schedules/week/${String(body.week_start)}/publication`;
    method = "GET";
    payload = null;
  } else if (body.operation === "publish_schedule") {
    path = `/api/v1/schedules/week/${String(body.week_start)}/publish`;
    payload = { notes: body.notes || null };
  } else if (body.operation === "review_requests") {
    path = "/api/v1/schedule/change-requests";
    method = "GET";
    payload = null;
  } else if (body.operation === "decide_request") {
    path = `/api/v1/schedule/change-requests/${Number(body.request_id)}/decision`;
    payload = { decision: body.decision, decision_note: body.decision_note || null, employee_notified: Boolean(body.employee_notified), coverage_confirmed: Boolean(body.coverage_confirmed), apply_change: body.apply_change !== false };
  }

  const response = await fetch(`${base()}${path}`, { method, headers: h, ...(method === "GET" ? {} : { body: JSON.stringify(payload) }), cache: "no-store" });
  return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
}
