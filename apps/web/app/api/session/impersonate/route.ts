import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import {
  ACCESS_TOKEN_COOKIE,
  NAME_COOKIE,
  OWNER_ACCESS_TOKEN_COOKIE,
  ROLE_COOKIE,
} from "@/lib/session-client";

export async function POST(request: Request) {
  const body = await request.json();
  const store = await cookies();
  const ownerToken = store.get(ACCESS_TOKEN_COOKIE)?.value;
  if (!ownerToken || store.get(OWNER_ACCESS_TOKEN_COOKIE)?.value) {
    return NextResponse.json({ ok: false, message: "Return to Owner before starting another view." }, { status: 409 });
  }

  const response = await fetch(`${apiBaseUrl()}/api/v1/auth/impersonate`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({ target_user_id: body.target_user_id }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    return NextResponse.json(data, { status: response.status });
  }

  const result = NextResponse.json({ ok: true, user: data.user });
  const cookieOptions = {
    path: "/",
    httpOnly: true,
    sameSite: "strict" as const,
    secure: process.env.NODE_ENV === "production",
    maxAge: Number(data.expires_in || 1800),
  };
  result.cookies.set(OWNER_ACCESS_TOKEN_COOKIE, ownerToken, cookieOptions);
  result.cookies.set(ACCESS_TOKEN_COOKIE, data.access_token, cookieOptions);
  result.cookies.set(ROLE_COOKIE, data.user.role_key, cookieOptions);
  result.cookies.set(NAME_COOKIE, data.user.display_name, cookieOptions);
  return result;
}
