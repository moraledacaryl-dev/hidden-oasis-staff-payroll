import { cookies } from "next/headers";
import { ACCESS_TOKEN_COOKIE, NAME_COOKIE, ROLE_COOKIE } from "./session-client";
import type { RoleKey } from "./types";

export const roles: RoleKey[] = ["owner", "payroll", "supervisor", "staff"];

export type WebSession = {
  id: number;
  display_name: string;
  role: string;
  role_key: RoleKey;
};

export function isRoleKey(value: string | undefined | null): value is RoleKey {
  return roles.includes(value as RoleKey);
}

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

export async function currentSession(): Promise<WebSession | null> {
  const store = await cookies();
  const token = store.get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return null;

  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/auth/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
        ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
      },
      cache: "no-store",
    });
    if (!response.ok) return null;
    const data = await response.json();
    const user = data.user;
    if (!isRoleKey(user?.role_key)) return null;
    return user as WebSession;
  } catch {
    return null;
  }
}

export async function currentRole(): Promise<RoleKey | null> {
  const session = await currentSession();
  if (session) return session.role_key;
  const store = await cookies();
  const raw = store.get(ROLE_COOKIE)?.value;
  return isRoleKey(raw) ? raw : null;
}

export async function currentName(): Promise<string> {
  const session = await currentSession();
  if (session) return session.display_name;
  const store = await cookies();
  return store.get(NAME_COOKIE)?.value || "Hidden Oasis User";
}
