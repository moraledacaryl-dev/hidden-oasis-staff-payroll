import { NextResponse } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { currentSession } from "@/lib/session";

export async function GET(request: Request) {
  const session = await currentSession();
  if (!session) {
    return NextResponse.json({ ok: false, message: "Not signed in." }, { status: 401 });
  }
  if (session.role_key === "staff") {
    return NextResponse.json(
      { ok: false, message: "Management access required." },
      { status: 403 },
    );
  }

  const url = new URL(request.url);
  const response = await fetch(
    `${apiBaseUrl()}/api/v1/hr/leave-balances?${url.searchParams.toString()}`,
    { headers: await backendHeaders(), cache: "no-store" },
  );
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
