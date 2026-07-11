"use client";

import Link from "next/link";
import { Bell, CalendarDays, CircleUserRound, Menu, Search, Users, WalletCards } from "lucide-react";
import { usePathname } from "next/navigation";
import { roleLabels } from "@/lib/navigation";
import type { RoleKey } from "@/lib/types";
import styles from "./WorkspaceChrome.module.css";

const labels: Array<[string, string]> = [
  ["/attendance/review", "Attendance Decisions"],
  ["/schedule/import", "Attendance Upload"],
  ["/schedule/requests", "Shift Requests"],
  ["/schedule", "Schedule"],
  ["/attendance", "Attendance"],
  ["/cash-advances", "Cash Advances"],
  ["/cutoff", "Cutoff Control"],
  ["/payroll/runs", "Payroll Runs"],
  ["/payroll", "Payroll"],
  ["/payslips", "Payslips"],
  ["/performance-reviews", "Performance Reviews"],
  ["/hr", "HR Records"],
  ["/staff", "Staff"],
  ["/reports", "Reports"],
  ["/backup", "Backups"],
  ["/settings", "Settings"],
  ["/me", "My Portal"],
  ["/", "Dashboard"],
];

function currentLabel(pathname: string) {
  return labels.find(([href]) => href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`))?.[1] || "Workspace";
}

function mobileItems(role: RoleKey) {
  if (role === "staff") {
    return [
      ["/me", "Home", CircleUserRound],
      ["/schedule", "Schedule", CalendarDays],
      ["/schedule/requests", "Requests", Users],
      ["/payslips", "Payslips", WalletCards],
    ] as const;
  }
  return [
    ["/", "Home", CircleUserRound],
    ["/schedule", "Schedule", CalendarDays],
    ["/attendance", "Attendance", Users],
    [role === "owner" || role === "payroll" ? "/cutoff" : "/staff", role === "owner" || role === "payroll" ? "Cutoff" : "People", WalletCards],
  ] as const;
}

export function WorkspaceChrome({ role }: { role: RoleKey }) {
  const pathname = usePathname();
  const label = currentLabel(pathname);
  const items = mobileItems(role);

  return (
    <>
      <header className={styles.topbar}>
        <div className={styles.topLeft}>
          <button className={styles.menuButton} type="button" aria-label="Open navigation" onClick={() => document.documentElement.setAttribute("data-sidebar-mobile-open", "true")}>
            <Menu size={18} />
          </button>
          <div className={styles.crumb}><span>Staff &amp; Payroll</span><b>/</b><strong>{label}</strong></div>
        </div>
        <div className={styles.actions}>
          <div className={styles.search} aria-label="Search shortcut"><Search size={16} /><span>Search staff, payroll, requests</span><kbd>⌘ K</kbd></div>
          <button className={styles.iconButton} type="button" aria-label="Notifications"><Bell size={18} /><span /></button>
          <div className={styles.roleSwitch} aria-label="Current role">{roleLabels[role]}</div>
        </div>
      </header>

      <nav className={styles.mobileNav} aria-label="Mobile navigation">
        {items.map(([href, text, Icon]) => {
          const active = href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
          return <Link href={href} key={href} className={active ? styles.active : ""}><Icon size={18} /><span>{text}</span></Link>;
        })}
      </nav>
    </>
  );
}
