import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const headers = await backendHeaders(true);
  if (!headers.Authorization) return NextResponse.json({ detail: "Not signed in." }, { status: 401 });
  const body = await request.json();
  const response = await fetch(`${apiBaseUrl()}/api/v1/users/${Number(id)}/role`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
