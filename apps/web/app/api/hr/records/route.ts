import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { currentSession } from "@/lib/session";

function denied(status: 401 | 403, message: string) {
  return NextResponse.json({ ok: false, message }, { status });
}

export async function GET(request: Request) {
  const session = await currentSession();
  if (!session) return denied(401, "Not signed in.");
  if (session.role_key === "staff") return denied(403, "Management access required.");

  const url = new URL(request.url);
  const response = await fetch(
    `${apiBaseUrl()}/api/v1/hr/records?${url.searchParams.toString()}`,
    { headers: await backendHeaders(), cache: "no-store" },
  );
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: Request) {
  const session = await currentSession();
  if (!session) return denied(401, "Not signed in.");
  if (session.role_key === "staff") return denied(403, "Management access required.");

  const response = await fetch(`${apiBaseUrl()}/api/v1/hr/records`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify(await request.json()),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/hr");
  return NextResponse.json(data, { status: response.status });
}
