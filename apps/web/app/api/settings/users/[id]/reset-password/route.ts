import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const headers = await backendHeaders();
  if (!headers.Authorization) return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  const response = await fetch(`${apiBaseUrl()}/api/v1/users/${Number(id)}/reset-password`, {
    method: "POST",
    headers,
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/settings/users");
  return NextResponse.json(data, { status: response.status });
}
