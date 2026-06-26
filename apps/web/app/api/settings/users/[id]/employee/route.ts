import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const headers = await backendHeaders(true);
  if (!headers.Authorization) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const body = await request.json();
  const employeeId = body.employee_id ? Number(body.employee_id) : null;
  const response = await fetch(`${apiBaseUrl()}/api/v1/users/${Number(id)}/employee`, {
    method: "POST",
    headers,
    body: JSON.stringify({ employee_id: employeeId }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
