import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { cookies } from "next/headers";
import { ACCESS_TOKEN_COOKIE, NAME_COOKIE, ROLE_COOKIE } from "./session-client";
import type { RoleKey } from "./types";

export const roles: RoleKey[] = ["owner", "payroll", "supervisor", "staff"];

export type WebSession = {
  id: number;
  display_name: string;
  role: string;
  role_key: RoleKey;
  must_change_password: number;
  mfa_enabled: number;
  mfa_setup_required: number;
  employee_id?: number | null;
  is_impersonating?: number;
  impersonator_id?: number | null;
  impersonator_name?: string | null;
};

export function isRoleKey(value: string | undefined | null): value is RoleKey {
  return roles.includes(value as RoleKey);
}

export async function currentSession(): Promise<WebSession | null> {
  const store = await cookies();
  const token = store.get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return null;

  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/auth/me`, {
      headers: await backendHeaders(),
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
