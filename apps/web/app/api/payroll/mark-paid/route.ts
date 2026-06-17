import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

export async function POST(request: Request) {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const body = await request.json();
  const runId = Number(body.run_id);
  if (!runId) return NextResponse.json({ ok: false, message: "Missing payroll run." }, { status: 422 });

  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${runId}/mark-paid`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    },
    body: JSON.stringify({ confirmation: body.confirmation, reference: body.reference || null }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    revalidatePath(`/payroll/runs/${runId}`);
    revalidatePath(`/payroll/runs/${runId}/audit`);
  }
  return NextResponse.json(data, { status: response.status });
}
