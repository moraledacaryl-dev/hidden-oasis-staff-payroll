import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE, NAME_COOKIE, ROLE_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

export async function POST(request: Request) {
  const body = await request.json();
  const apiResponse = await fetch(`${apiBaseUrl()}/api/v1/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    },
    body: JSON.stringify({ display_name: body.display_name, password: body.password }),
    cache: "no-store",
  });

  if (!apiResponse.ok) {
    return NextResponse.json({ ok: false, message: "Invalid username or password." }, { status: 401 });
  }

  const data = await apiResponse.json();
  const result = NextResponse.json({ ok: true, user: data.user });
  const cookieOptions = { path: "/", httpOnly: true, sameSite: "lax" as const, secure: process.env.NODE_ENV === "production", maxAge: Number(data.expires_in || 43200) };
  result.cookies.set(ACCESS_TOKEN_COOKIE, data.access_token, cookieOptions);
  result.cookies.set(ROLE_COOKIE, data.user.role_key, cookieOptions);
  result.cookies.set(NAME_COOKIE, data.user.display_name, cookieOptions);
  return result;
}
