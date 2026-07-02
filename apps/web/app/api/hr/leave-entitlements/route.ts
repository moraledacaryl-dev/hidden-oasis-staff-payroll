import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { currentSession } from "@/lib/session";

function denied(status: 401 | 403, message: string) {
  return NextResponse.json({ ok: false, message }, { status });
}

export async function POST(request: Request) {
  const session = await currentSession();
  if (!session) return denied(401, "Not signed in.");
  if (!["owner", "payroll"].includes(session.role_key)) return denied(403, "Only owner or payroll can edit leave entitlements.");

  const response = await fetch(`${apiBaseUrl()}/api/v1/hr/leave-entitlements`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify(await request.json()),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/hr");
  return NextResponse.json(data, { status: response.status });
}
