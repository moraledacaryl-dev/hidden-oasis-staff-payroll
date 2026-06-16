import type { RoleKey } from "./types";

export type NavItem = {
  href: string;
  label: string;
  description: string;
  roles: RoleKey[];
};

export const navItems: NavItem[] = [
  {
    href: "/",
    label: "Command Center",
    description: "Owner overview, API status, labor and payroll readiness.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/staff",
    label: "Staff",
    description: "Staff list, departments, employment status, benefit toggles.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/supervisor",
    label: "Supervisor",
    description: "Attendance exceptions, OT, leaves, and daily action queue.",
    roles: ["owner", "supervisor"],
  },
  {
    href: "/payroll",
    label: "Payroll",
    description: "Cutoff QA and preview through the existing Python payroll engine.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/owner",
    label: "Owner",
    description: "Approval cockpit for labor cost, net pay, cash advances, and sync status.",
    roles: ["owner"],
  },
  {
    href: "/reports",
    label: "Reports",
    description: "Labor summaries, deductions, cash advances, and export readiness.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/settings",
    label: "Settings",
    description: "Migration status, API settings, permissions, and do-not-break rules.",
    roles: ["owner"],
  },
];

export const roleLabels: Record<RoleKey, string> = {
  owner: "Owner",
  payroll: "Payroll Admin",
  supervisor: "Supervisor",
  staff: "Staff Portal",
};
