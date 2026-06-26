import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function GET() {
  const response = await fetch(`${apiBaseUrl()}/api/v1/hr/leave-requests`, {
    headers: await backendHeaders(),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: Request) {
  const body = await request.json();
  const response = await fetch(
    `${apiBaseUrl()}/api/v1/hr/leave-requests/${Number(body.request_id)}/decision`,
    {
      method: "POST",
      headers: await backendHeaders(true),
      body: JSON.stringify({ status: body.status, decision_note: body.decision_note }),
      cache: "no-store",
    },
  );
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/hr");
  return NextResponse.json(data, { status: response.status });
}
