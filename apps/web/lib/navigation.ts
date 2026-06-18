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
    description: "Payroll status.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/cutoff",
    label: "Cutoff Control",
    description: "Save and review.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/schedule",
    label: "Schedule",
    description: "Weekly board.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/hr",
    label: "HR Records",
    description: "Leave, reviews, memos.",
    roles: ["owner", "payroll", "supervisor", "staff"],
  },
  {
    href: "/payroll/runs",
    label: "Payroll Runs",
    description: "Run history.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/backup",
    label: "Backups",
    description: "Data safety.",
    roles: ["owner"],
  },
  {
    href: "/launch",
    label: "Launch Check",
    description: "Health checks.",
    roles: ["owner"],
  },
  {
    href: "/controls",
    label: "Controls",
    description: "Shortcuts.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/me",
    label: "My Portal",
    description: "Staff view.",
    roles: ["staff"],
  },
  {
    href: "/staff",
    label: "Staff",
    description: "Directory.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/supervisor",
    label: "Supervisor",
    description: "Action queue.",
    roles: ["owner", "supervisor"],
  },
  {
    href: "/payroll",
    label: "Payroll Preview",
    description: "Cutoff totals.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/owner",
    label: "Owner",
    description: "Approval view.",
    roles: ["owner"],
  },
  {
    href: "/reports",
    label: "Reports",
    description: "Summaries.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/settings",
    label: "Settings",
    description: "System tools.",
    roles: ["owner"],
  },
  {
    href: "/settings/password",
    label: "Password",
    description: "Change password.",
    roles: ["owner", "payroll", "supervisor", "staff"],
  },
];

export const roleLabels: Record<RoleKey, string> = {
  owner: "Owner",
  payroll: "Payroll Admin",
  supervisor: "Supervisor",
  staff: "Staff Portal",
};