import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function PUT(request: Request, context: { params: Promise<{ id: string }> }) {
  const headers = await backendHeaders(true);
  if (!headers.Authorization) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const { id } = await context.params;
  const response = await fetch(`${apiBaseUrl()}/api/v1/holidays/${encodeURIComponent(id)}`, { method: "PUT", headers, body: JSON.stringify(await request.json()), cache: "no-store" });
  return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
}
