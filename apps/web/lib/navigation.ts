import type { RoleKey } from "./types";

export type NavItem = {
  href: string;
  label: string;
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
      { href: "/", label: "Dashboard", roles: ["owner", "payroll", "supervisor"] },
      { href: "/me", label: "My Dashboard", roles: ["staff"] },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/schedule", label: "Schedule", roles: ["owner", "payroll", "supervisor"] },
      { href: "/schedule/requests", label: "Shift Requests", roles: ["owner", "payroll", "supervisor"] },
      { href: "/attendance", label: "Attendance", roles: ["owner", "supervisor"] },
    ],
  },
  {
    label: "People",
    items: [
      { href: "/staff", label: "Staff Directory", roles: ["owner", "payroll", "supervisor"] },
      { href: "/performance-reviews", label: "Performance Reviews", roles: ["owner", "supervisor"] },
      { href: "/hr", label: "HR Records", roles: ["owner", "payroll", "supervisor"] },
      { href: "/cash-advances", label: "Cash Advances", roles: ["owner", "payroll", "supervisor"] },
    ],
  },
  {
    label: "Payroll",
    items: [
      { href: "/cutoff", label: "Cutoff Control", roles: ["owner", "payroll", "supervisor"] },
      { href: "/payroll", label: "Payroll Preview", roles: ["owner", "payroll"] },
      { href: "/payroll/runs", label: "Payroll Runs", roles: ["owner", "payroll"] },
      { href: "/payslips", label: "Payslip Distribution", roles: ["owner", "payroll", "supervisor"] },
      { href: "/reports/operations", label: "Reports", roles: ["supervisor"] },
      { href: "/reports", label: "Reports", roles: ["owner", "payroll"] },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/controls", label: "System Controls", roles: ["owner", "payroll"] },
      { href: "/backup", label: "Backups", roles: ["owner"] },
      { href: "/settings", label: "Settings", roles: ["owner"] },
    ],
  },
  {
    label: null,
    items: [
      { href: "/settings/password", label: "Account", roles: ["owner", "payroll", "supervisor", "staff"] },
    ],
  },
];

export const navItems: NavItem[] = navGroups.flatMap((group) => group.items);

export const roleLabels: Record<RoleKey, string> = {
  owner: "Owner",
  payroll: "Payroll Admin",
  supervisor: "General Manager",
  staff: "Staff Portal",
};
