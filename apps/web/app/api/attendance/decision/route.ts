import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json();
  const response = await fetch(`${apiBaseUrl()}/api/v1/attendance/time-logs/${body.time_log_id}/decision`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({
      decision: body.decision,
      reason: body.reason || "Reviewed from the attendance queue.",
      approved_ot_hours: Number(body.approved_ot_hours || 0),
    }),
    cache: "no-store",
  });

  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
