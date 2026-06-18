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
    label: "Dashboard",
    description: "Overview.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/cutoff",
    label: "Cutoff Control",
    description: "Review cycle.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/schedule",
    label: "Schedule",
    description: "Weekly board.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/attendance",
    label: "Attendance Review",
    description: "Exceptions and OT.",
    roles: ["owner", "supervisor"],
  },
  {
    href: "/payslips",
    label: "Payslip Distribution",
    description: "Print and release.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/hr",
    label: "HR Records",
    description: "Leave, reviews, memos.",
    roles: ["owner", "payroll", "supervisor", "staff"],
  },
  {
    href: "/staff",
    label: "Staff Directory",
    description: "Employee profiles.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/reports",
    label: "Reports",
    description: "Summaries.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/payroll/runs",
    label: "Payroll Runs",
    description: "Run history.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/payroll",
    label: "Payroll Preview",
    description: "Cutoff totals.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/controls",
    label: "System Controls",
    description: "Operations.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/backup",
    label: "Backups",
    description: "Data safety.",
    roles: ["owner"],
  },
  {
    href: "/settings",
    label: "Settings",
    description: "Configuration.",
    roles: ["owner"],
  },
  {
    href: "/settings/password",
    label: "Account",
    description: "Password.",
    roles: ["owner", "payroll", "supervisor", "staff"],
  },
  {
    href: "/me",
    label: "My Dashboard",
    description: "Staff portal.",
    roles: ["staff"],
  },
];

export const roleLabels: Record<RoleKey, string> = {
  owner: "Owner",
  payroll: "Payroll Admin",
  supervisor: "Supervisor",
  staff: "Staff Portal",
};