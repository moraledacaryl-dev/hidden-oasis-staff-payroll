import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const headers = await backendHeaders(true);
  if (!headers.Authorization) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const body = await request.json();
  const response = await fetch(`${apiBaseUrl()}/api/v1/users/${Number(id)}/active`, {
    method: "POST",
    headers,
    body: JSON.stringify({ active: Boolean(body.active) }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/settings/users");
  return NextResponse.json(data, { status: response.status });
}
