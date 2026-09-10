import { mondayOfWeek } from "./period";
import type { RoleKey } from "./types";

export function payrollCheckHref(category: string, role: RoleKey, start: string, end: string): string {
  const period = new URLSearchParams({ start, end }).toString();
  if (/employee|rate|salary|compensation|benefit/i.test(category)) return "/staff/manage?setup=compensation";
  if (/cash|advance/i.test(category)) return "/cash-advances";
  if (/attendance|overtime|time log|absence/i.test(category)) return role === "payroll" ? `/schedule?week_start=${mondayOfWeek(start)}` : `/attendance/review?${period}`;
  if (/leave/i.test(category)) return "/hr";
  if (/holiday/i.test(category)) return "/payroll/holidays";
  return `/payroll?${period}`;
}
