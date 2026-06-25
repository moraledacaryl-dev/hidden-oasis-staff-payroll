import type { RoleKey } from "./types";

export type NavItem = {
  href: string;
  label: string;
  description: string;
  roles: RoleKey[];
};

export type NavGroup = {
  label: string | null;
  items: NavItem[];
};

export const navGroups: NavGroup[] = [
  {
    label: null,
    items: [
      { href: "/", label: "Dashboard", description: "Overview.", roles: ["owner", "payroll", "supervisor"] },
      { href: "/me", label: "My Dashboard", description: "Staff portal.", roles: ["staff"] },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/schedule", label: "Schedule", description: "Weekly board.", roles: ["owner", "payroll", "supervisor"] },
      { href: "/schedule/requests", label: "Shift Requests", description: "Review schedule changes.", roles: ["owner", "payroll", "supervisor"] },
      { href: "/attendance", label: "Attendance", description: "Review and compliance.", roles: ["owner", "supervisor"] },
    ],
  },
  {
    label: "People",
    items: [
      { href: "/staff", label: "Staff Directory", description: "Employee profiles.", roles: ["owner", "payroll", "supervisor"] },
      { href: "/performance-reviews", label: "Performance Reviews", description: "Annual staff reviews.", roles: ["owner", "supervisor"] },
      { href: "/hr", label: "HR Records", description: "Leave and formal records.", roles: ["owner", "payroll", "supervisor"] },
      { href: "/cash-advances", label: "Cash Advances", description: "Advances and balances.", roles: ["owner", "payroll", "supervisor"] },
    ],
  },
  {
    label: "Payroll",
    items: [
      { href: "/cutoff", label: "Cutoff Control", description: "Review cycle.", roles: ["owner", "payroll", "supervisor"] },
      { href: "/payroll", label: "Payroll Preview", description: "Cutoff totals.", roles: ["owner", "payroll"] },
      { href: "/payroll/runs", label: "Payroll Runs", description: "Run history.", roles: ["owner", "payroll"] },
      { href: "/payslips", label: "Payslip Distribution", description: "Print and release.", roles: ["owner", "payroll", "supervisor"] },
      { href: "/reports/operations", label: "Reports", description: "Operational summaries.", roles: ["supervisor"] },
      { href: "/reports", label: "Reports", description: "Payroll summaries.", roles: ["owner", "payroll"] },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/controls", label: "System Controls", description: "Operations.", roles: ["owner", "payroll"] },
      { href: "/backup", label: "Backups", description: "Data safety.", roles: ["owner"] },
      { href: "/settings", label: "Settings", description: "Configuration.", roles: ["owner"] },
    ],
  },
  {
    label: null,
    items: [
      { href: "/settings/password", label: "Account", description: "Password.", roles: ["owner", "payroll", "supervisor", "staff"] },
    ],
  },
];

export const navItems: NavItem[] = navGroups.flatMap((group) => group.items);

export const roleLabels: Record<RoleKey, string> = {
  owner: "Owner",
  payroll: "Payroll Admin",
  supervisor: "Supervisor",
  staff: "Staff Portal",
};
