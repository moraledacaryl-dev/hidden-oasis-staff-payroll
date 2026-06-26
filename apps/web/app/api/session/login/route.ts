import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE, NAME_COOKIE, ROLE_COOKIE } from "@/lib/session-client";

export async function POST(request: Request) {
  const body = await request.json();
  const apiResponse = await fetch(`${apiBaseUrl()}/api/v1/auth/login`, {
    method: "POST",
    headers: await backendHeaders(true, false),
    body: JSON.stringify({ display_name: body.display_name, password: body.password, otp: body.otp }),
    cache: "no-store",
  });

  if (!apiResponse.ok) {
    const failed = await apiResponse.json().catch(() => ({}));
    return NextResponse.json(
      { ok: false, message: failed.detail || "Sign in failed." },
      { status: apiResponse.status },
    );
  }

  const data = await apiResponse.json();
  const result = NextResponse.json({ ok: true, user: data.user });
  const cookieOptions = { path: "/", httpOnly: true, sameSite: "lax" as const, secure: process.env.NODE_ENV === "production", maxAge: Number(data.expires_in || 43200) };
  result.cookies.set(ACCESS_TOKEN_COOKIE, data.access_token, cookieOptions);
  result.cookies.set(ROLE_COOKIE, data.user.role_key, cookieOptions);
  result.cookies.set(NAME_COOKIE, data.user.display_name, cookieOptions);
  return result;
}
