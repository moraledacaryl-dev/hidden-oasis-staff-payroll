import { cookies } from "next/headers";
import type { RoleKey } from "./types";

export const ROLE_COOKIE = "ho_staff_payroll_role";
export const NAME_COOKIE = "ho_staff_payroll_name";

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

export function defaultPathForRole(role: RoleKey): string {
  switch (role) {
    case "owner":
      return "/";
    case "payroll":
      return "/payroll";
    case "supervisor":
      return "/supervisor";
    case "staff":
      return "/me";
    default:
      return "/";
  }
}
