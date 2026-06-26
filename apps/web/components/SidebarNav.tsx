"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Banknote,
  CalendarDays,
  ChartNoAxesCombined,
  CircleUserRound,
  ClipboardCheck,
  Clock3,
  DatabaseBackup,
  FileClock,
  FileText,
  HandCoins,
  History,
  LayoutDashboard,
  ListChecks,
  LockKeyhole,
  ReceiptText,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Star,
  Users,
  type LucideIcon,
} from "lucide-react";
import { navGroups } from "@/lib/navigation";
import type { RoleKey } from "@/lib/types";
import styles from "./SidebarNav.module.css";

const icons: Record<string, LucideIcon> = {
  "/": LayoutDashboard,
  "/me": CircleUserRound,
  "/schedule": CalendarDays,
  "/schedule/requests": FileClock,
  "/attendance": Clock3,
  "/staff": Users,
  "/performance-reviews": Star,
  "/hr": FileText,
  "/cash-advances": HandCoins,
  "/cutoff": ClipboardCheck,
  "/payroll": Banknote,
  "/payroll/runs": History,
  "/payslips": ReceiptText,
  "/reports/operations": ListChecks,
  "/reports": ChartNoAxesCombined,
  "/controls": SlidersHorizontal,
  "/backup": DatabaseBackup,
  "/settings": Settings,
  "/settings/security": ShieldCheck,
  "/settings/password": LockKeyhole,
};

function routeMatches(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function activeHrefFor(pathname: string, hrefs: string[]): string | null {
  return hrefs
    .filter((href) => routeMatches(pathname, href))
    .sort((a, b) => b.length - a.length)[0] || null;
}

function NavLink({ href, label, active, subcard = false }: {
  href: string;
  label: string;
  active: boolean;
  subcard?: boolean;
}) {
  const Icon = icons[href] || FileText;
  return (
    <Link
      className={`nav-card ${styles.link} ${subcard ? styles.subcard : ""} ${active ? styles.activeLink : ""}`}
      href={href}
      title={label}
      aria-current={active ? "page" : undefined}
    >
      <span className={styles.glyph} aria-hidden="true"><Icon size={17} strokeWidth={1.9} /></span>
      <span className={styles.copy}>
        <strong>{label}</strong>
      </span>
    </Link>
  );
}

export function SidebarNav({ role }: { role: RoleKey }) {
  const pathname = usePathname();
  const visibleHrefs = navGroups
    .flatMap((group) => group.items)
    .filter((item) => item.roles.includes(role))
    .map((item) => item.href);
  const activeHref = activeHrefFor(pathname, visibleHrefs);

  return (
    <nav className={`nav-list ${styles.nav}`} aria-label="Main navigation">
      {navGroups.map((group, groupIndex) => {
        const items = group.items.filter((item) => item.roles.includes(role));
        if (!items.length) return null;

        const groupActive = items.some((item) => item.href === activeHref);

        if (!group.label) {
          return (
            <div className={styles.standalone} key={`standalone-${groupIndex}`}>
              {items.map((item) => (
                <NavLink
                  key={item.href}
                  href={item.href}
                  label={item.label}
                  active={item.href === activeHref}
                />
              ))}
            </div>
          );
        }

        return (
          <details
            className={styles.group}
            open={groupActive || undefined}
            key={`${group.label}-${pathname}`}
          >
            <summary className={groupActive ? styles.active : ""} title={group.label}>
              <strong>{group.label}</strong>
              <span className={styles.chevron} aria-hidden="true">›</span>
            </summary>
            <div className={styles.sublist}>
              {items.map((item) => (
                <NavLink
                  key={item.href}
                  href={item.href}
                  label={item.label}
                  active={item.href === activeHref}
                  subcard
                />
              ))}
            </div>
          </details>
        );
      })}
    </nav>
  );
}
