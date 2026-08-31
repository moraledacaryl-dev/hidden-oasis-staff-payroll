import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function GET() {
  const headers = await backendHeaders();
  if (!headers.Authorization) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const response = await fetch(`${apiBaseUrl()}/api/v1/holidays`, { headers, cache: "no-store" });
  return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
}

export async function POST(request: Request) {
  const headers = await backendHeaders(true);
  if (!headers.Authorization) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const response = await fetch(`${apiBaseUrl()}/api/v1/holidays`, { method: "POST", headers, body: JSON.stringify(await request.json()), cache: "no-store" });
  return NextResponse.json(await response.json().catch(() => ({})), { status: response.status });
}
