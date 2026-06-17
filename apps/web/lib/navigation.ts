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
    href: "/cutoff",
    label: "Cutoff Control",
    description: "Payroll QA, attendance exceptions, and review history.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/schedule",
    label: "Schedule",
    description: "Weekly planned schedule board, filters, copy week, and shift creation.",
    roles: ["owner", "payroll", "supervisor"],
  },
  {
    href: "/payroll/runs",
    label: "Payroll Runs",
    description: "Saved payroll runs, audit timeline, reports, and payslips.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/backup",
    label: "Backups",
    description: "Backup checklist and production data safety checks.",
    roles: ["owner"],
  },
  {
    href: "/launch",
    label: "Launch Check",
    description: "Production health, service readiness, and deployment checklist.",
    roles: ["owner"],
  },
  {
    href: "/controls",
    label: "Controls",
    description: "Operational shortcuts and protected production controls.",
    roles: ["owner", "payroll"],
  },
  {
    href: "/me",
    label: "My Portal",
    description: "Personal schedule, leave, payslip, and request shell.",
    roles: ["staff"],
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
    label: "Payroll Preview",
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
  {
    href: "/settings/password",
    label: "Password",
    description: "Change your own sign-in password.",
    roles: ["owner", "payroll", "supervisor", "staff"],
  },
];

export const roleLabels: Record<RoleKey, string> = {
  owner: "Owner",
  payroll: "Payroll Admin",
  supervisor: "Supervisor",
  staff: "Staff Portal",
};
