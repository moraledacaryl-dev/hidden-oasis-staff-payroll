import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE, NAME_COOKIE, OWNER_ACCESS_TOKEN_COOKIE, ROLE_COOKIE } from "@/lib/session-client";

export async function POST() {
  const result = NextResponse.json({ ok: true });
  result.cookies.delete(ACCESS_TOKEN_COOKIE);
  result.cookies.delete(OWNER_ACCESS_TOKEN_COOKIE);
  result.cookies.delete(ROLE_COOKIE);
  result.cookies.delete(NAME_COOKIE);
  return result;
}
