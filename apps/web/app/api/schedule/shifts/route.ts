import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function GET() {
  const h = await backendHeaders();
  const response = await fetch(`${apiBaseUrl()}/api/v1/me/published-self-service`, { headers: h, cache: "no-store" });
  return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
}

export async function POST(request: Request) {
  const multipart = (request.headers.get("content-type") || "").includes("multipart/form-data");
  const h = await backendHeaders(!multipart);

  if (multipart) {
    const incoming = await request.formData();
    const id = Number(incoming.get("request_id") || 0);
    const file = incoming.get("file");
    if (!id || !(file instanceof File)) return NextResponse.json({ ok: false, message: "Request and file are required." }, { status: 422 });
    const outgoing = new FormData();
    outgoing.set("file", file);
    const response = await fetch(`${apiBaseUrl()}/api/v1/me/shift-change-requests/${id}/attachment`, { method: "POST", headers: h, body: outgoing, cache: "no-store" });
    return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
  }

  const body = await request.json();
  let path = "/api/v1/schedules/shifts";
  let payload: unknown = body;
  let method = "POST";

  if (body.operation === "staff_request") {
    path = "/api/v1/me/shift-change-requests";
    payload = Object.fromEntries(Object.entries(body).filter(([key]) => key !== "operation"));
  } else if (body.operation === "leave_request") {
    path = "/api/v1/me/leave-requests";
    payload = Object.fromEntries(Object.entries(body).filter(([key]) => key !== "operation"));
  } else if (body.operation === "withdraw_leave_request") {
    path = `/api/v1/me/leave-requests/${Number(body.request_id)}/withdraw`;
    payload = {};
  } else if (body.operation === "withdraw_request") {
    path = `/api/v1/me/shift-change-requests/${Number(body.request_id)}/withdraw`;
    payload = {};
  } else if (body.operation === "confirm_swap") {
    path = `/api/v1/me/shift-change-requests/${Number(body.request_id)}/confirm-swap`;
    payload = {};
  } else if (body.operation === "decline_swap") {
    path = `/api/v1/me/shift-change-requests/${Number(body.request_id)}/decline-swap`;
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

  const response = await fetch(`${apiBaseUrl()}${path}`, { method, headers: h, ...(method === "GET" ? {} : { body: JSON.stringify(payload) }), cache: "no-store" });
  return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
}
