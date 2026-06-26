import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE, NAME_COOKIE, ROLE_COOKIE } from "@/lib/session-client";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const action = body.action;
  const path =
    action === "setup"
      ? "/api/v1/auth/mfa/setup"
      : action === "confirm"
        ? "/api/v1/auth/mfa/confirm"
        : action === "disable"
          ? "/api/v1/auth/mfa/disable"
          : null;
  if (!path) return NextResponse.json({ detail: "Invalid action." }, { status: 400 });

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  const result = NextResponse.json(data, { status: response.status });
  if (response.ok && action !== "setup") {
    result.cookies.delete(ACCESS_TOKEN_COOKIE);
    result.cookies.delete(ROLE_COOKIE);
    result.cookies.delete(NAME_COOKIE);
  }
  return result;
}
