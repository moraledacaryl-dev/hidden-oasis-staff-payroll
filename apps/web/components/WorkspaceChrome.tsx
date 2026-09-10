"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CalendarDays, CircleUserRound, Menu, Users, WalletCards } from "lucide-react";
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
  ["/staff/manage", "Manage workers"],
  ["/staff", "Staff"],
  ["/reports", "Reports"],
  ["/backup", "Backups"],
  ["/settings/security", "Account security"],
  ["/settings/password", "Change password"],
  ["/settings/users", "User management"],
  ["/settings/controls", "Payroll controls"],
  ["/controls", "System Controls"],
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
      ["/me#my-schedule", "Schedule", CalendarDays],
      ["/me#my-requests", "Requests", Users],
      ["/me#my-payslips", "Payslips", WalletCards],
    ] as const;
  }
  return [
    ["/", "Home", CircleUserRound],
    ["/schedule", "Schedule", CalendarDays],
    [role === "payroll" ? "/payroll" : "/attendance/review", role === "payroll" ? "Payroll" : "Attendance", Users],
    [role === "owner" || role === "payroll" ? "/cutoff" : "/staff", role === "owner" || role === "payroll" ? "Cutoff" : "People", WalletCards],
  ] as const;
}

export function WorkspaceChrome({ role }: { role: RoleKey }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [hash, setHash] = useState("");
  useEffect(() => {
    const sync = () => { setMenuOpen(document.documentElement.hasAttribute("data-sidebar-mobile-open")); setHash(window.location.hash); };
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-sidebar-mobile-open"] });
    window.addEventListener("hashchange", sync); sync();
    return () => { observer.disconnect(); window.removeEventListener("hashchange", sync); };
  }, [pathname]);
  const label = currentLabel(pathname);
  const items = mobileItems(role);

  return (
    <>
      <header className={styles.topbar}>
        <div className={styles.topLeft}>
          <button className={styles.menuButton} type="button" aria-label="Open navigation" aria-expanded={menuOpen} aria-controls="workspace-navigation" onClick={() => document.documentElement.setAttribute("data-sidebar-mobile-open", "true")}>
            <Menu size={18} />
          </button>
          <div className={styles.crumb}><span>Staff &amp; Payroll</span><b>/</b><strong>{label}</strong></div>
        </div>
        <div className={styles.actions}>
          <div className={styles.roleSwitch} aria-label="Current role">{roleLabels[role]}</div>
        </div>
      </header>

      <nav className={styles.mobileNav} aria-label="Mobile navigation">
        {items.map(([href, text, Icon]) => {
          const active = href.includes("#") ? `${pathname}${hash}` === href : href === "/" || href === "/me" ? pathname === href && !hash : pathname === href || pathname.startsWith(`${href}/`);
          return <Link href={href} key={href} aria-current={active ? "page" : undefined} onClick={() => setHash(href.includes("#") ? `#${href.split("#")[1]}` : "")} className={active ? styles.active : ""}><Icon size={18} /><span>{text}</span></Link>;
        })}
      </nav>
    </>
  );
}
