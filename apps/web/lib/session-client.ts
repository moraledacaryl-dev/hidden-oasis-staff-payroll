import type { RoleKey } from "./types";

export const ROLE_COOKIE = "ho_staff_payroll_role";
export const NAME_COOKIE = "ho_staff_payroll_name";

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
