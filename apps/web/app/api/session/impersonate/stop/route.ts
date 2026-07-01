import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import {
  ACCESS_TOKEN_COOKIE,
  NAME_COOKIE,
  OWNER_ACCESS_TOKEN_COOKIE,
  ROLE_COOKIE,
} from "@/lib/session-client";

export async function POST() {
  const store = await cookies();
  const ownerToken = store.get(OWNER_ACCESS_TOKEN_COOKIE)?.value;
  if (!ownerToken) {
    return NextResponse.json({ ok: false, message: "Owner session is unavailable." }, { status: 409 });
  }

  const baseHeaders = await backendHeaders(false, false);
  const ownerResponse = await fetch(`${apiBaseUrl()}/api/v1/auth/me`, {
    headers: { ...baseHeaders, Authorization: `Bearer ${ownerToken}` },
    cache: "no-store",
  });
  const ownerData = await ownerResponse.json().catch(() => ({}));
  if (!ownerResponse.ok || ownerData.user?.role_key !== "owner") {
    const failed = NextResponse.json({ ok: false, message: "Owner session expired. Sign in again." }, { status: 401 });
    failed.cookies.delete(ACCESS_TOKEN_COOKIE);
    failed.cookies.delete(OWNER_ACCESS_TOKEN_COOKIE);
    failed.cookies.delete(ROLE_COOKIE);
    failed.cookies.delete(NAME_COOKIE);
    return failed;
  }

  const viewedToken = store.get(ACCESS_TOKEN_COOKIE)?.value;
  let targetUserId: number | null = null;
  if (viewedToken) {
    const viewedResponse = await fetch(`${apiBaseUrl()}/api/v1/auth/me`, {
      headers: { ...baseHeaders, Authorization: `Bearer ${viewedToken}` },
      cache: "no-store",
    });
    const viewedData = await viewedResponse.json().catch(() => ({}));
    targetUserId = Number(viewedData.user?.id) || null;
  }
  await fetch(`${apiBaseUrl()}/api/v1/auth/impersonate/end`, {
    method: "POST",
    headers: { ...(await backendHeaders(true, false)), Authorization: `Bearer ${ownerToken}` },
    body: JSON.stringify({ target_user_id: targetUserId }),
    cache: "no-store",
  }).catch(() => null);

  const result = NextResponse.json({ ok: true, user: ownerData.user });
  const cookieOptions = {
    path: "/",
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    maxAge: 43200,
  };
  result.cookies.set(ACCESS_TOKEN_COOKIE, ownerToken, cookieOptions);
  result.cookies.set(ROLE_COOKIE, ownerData.user.role_key, cookieOptions);
  result.cookies.set(NAME_COOKIE, ownerData.user.display_name, cookieOptions);
  result.cookies.delete(OWNER_ACCESS_TOKEN_COOKIE);
  return result;
}
