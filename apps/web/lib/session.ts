import { cookies } from "next/headers";
import { NAME_COOKIE, ROLE_COOKIE } from "./session-client";
import type { RoleKey } from "./types";

export const roles: RoleKey[] = ["owner", "payroll", "supervisor", "staff"];

export function isRoleKey(value: string | undefined | null): value is RoleKey {
  return roles.includes(value as RoleKey);
}

export async function currentRole(): Promise<RoleKey | null> {
  const store = await cookies();
  const raw = store.get(ROLE_COOKIE)?.value;
  return isRoleKey(raw) ? raw : null;
}

export async function currentName(): Promise<string> {
  const store = await cookies();
  return store.get(NAME_COOKIE)?.value || "Hidden Oasis User";
}
