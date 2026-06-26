import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json();
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/copy-week`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({ from_week_start: body.from_week_start, to_week_start: body.to_week_start }),
    cache: "no-store",
  });

  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
