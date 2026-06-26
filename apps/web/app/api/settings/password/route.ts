import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE, NAME_COOKIE, ROLE_COOKIE } from "@/lib/session-client";

export async function POST(request: Request) {
  const body = await request.json();
  const response = await fetch(`${apiBaseUrl()}/api/v1/auth/change-password`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({ current_password: body.current_password, new_password: body.new_password }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  const result = NextResponse.json(data, { status: response.status });
  if (response.ok) {
    result.cookies.delete(ACCESS_TOKEN_COOKIE);
    result.cookies.delete(ROLE_COOKIE);
    result.cookies.delete(NAME_COOKIE);
  }
  return result;
}
