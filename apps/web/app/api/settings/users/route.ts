import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function GET() {
  const headers = await backendHeaders();
  if (!headers.Authorization) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const response = await fetch(`${apiBaseUrl()}/api/v1/users`, {
    headers,
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}


export async function POST(request: Request) {
  const headers = await backendHeaders(true);
  if (!headers.Authorization) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const body = await request.json();
  const response = await fetch(`${apiBaseUrl()}/api/v1/users`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
