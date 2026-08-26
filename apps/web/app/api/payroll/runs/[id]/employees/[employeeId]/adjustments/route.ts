import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { randomUUID } from "crypto";

export async function GET(_: Request, { params }: { params: Promise<{ id: string; employeeId: string }> }) {
  const { id, employeeId } = await params;
  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${id}/employees/${employeeId}/adjustments`, { headers: await backendHeaders(), cache: "no-store" });
  return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string; employeeId: string }> }) {
  const { id, employeeId } = await params;
  const headers = await backendHeaders(true);
  headers.set("X-Request-ID", request.headers.get("X-Request-ID") || randomUUID());
  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${id}/employees/${employeeId}/adjustments`, {
    method: "POST",
    headers,
    body: JSON.stringify(await request.json()),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    revalidatePath(`/payroll/runs/${id}`);
    revalidatePath(`/payroll/runs/${id}/audit`);
  }
  return NextResponse.json(data, { status: response.status });
}
