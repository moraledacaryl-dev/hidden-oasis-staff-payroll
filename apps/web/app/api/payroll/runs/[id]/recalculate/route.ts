import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function POST(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${id}/recalculate`, {
    method: "POST",
    headers: await backendHeaders(),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
