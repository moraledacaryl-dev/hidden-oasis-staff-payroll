"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
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
  Upload,
  Users,
  type LucideIcon,
} from "lucide-react";
import { navGroups } from "@/lib/navigation";
import type { RoleKey } from "@/lib/types";
import styles from "./SidebarNav.module.css";

const SIDEBAR_SCROLL_KEY = "hidden-oasis-staff-sidebar-scroll";

const icons: Record<string, LucideIcon> = {
  "/": LayoutDashboard,
  "/me": CircleUserRound,
  "/schedule": CalendarDays,
  "/schedule/import": Upload,
  "/schedule/requests": FileClock,
  "/attendance": Clock3,
  "/attendance/review": ClipboardCheck,
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
  return hrefs.filter((href) => routeMatches(pathname, href)).sort((a, b) => b.length - a.length)[0] || null;
}

export function SidebarNav({ role }: { role: RoleKey }) {
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);
  const visibleItems = navGroups.flatMap((group) => group.items).filter((item) => item.roles.includes(role));
  const activeHref = activeHrefFor(pathname, visibleItems.map((item) => item.href));

  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;

    const stored = Number.parseFloat(sessionStorage.getItem(SIDEBAR_SCROLL_KEY) || "0");
    const target = Number.isFinite(stored) ? stored : 0;

    // Restore after layout and once more after route content settles. This prevents
    // focus/layout changes from snapping the navigation back to its first item.
    const firstFrame = window.requestAnimationFrame(() => {
      nav.scrollTop = target;
    });
    const settleTimer = window.setTimeout(() => {
      nav.scrollTop = target;
    }, 80);

    const remember = () => {
      sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(nav.scrollTop));
    };

    nav.addEventListener("scroll", remember, { passive: true });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      window.clearTimeout(settleTimer);
      remember();
      nav.removeEventListener("scroll", remember);
    };
  }, [pathname]);

  const rememberSidebarPosition = () => {
    const nav = navRef.current;
    if (nav) {
      sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(nav.scrollTop));
    }
    document.documentElement.removeAttribute("data-sidebar-mobile-open");
  };

  return (
    <nav className={styles.nav} aria-label="Main navigation" ref={navRef}>
      {navGroups.map((group, index) => {
        const items = group.items.filter((item) => item.roles.includes(role));
        if (!items.length) return null;
        return (
          <section className={styles.section} key={`${group.label || "primary"}-${index}`}>
            {group.label ? <div className={styles.label}>{group.label}</div> : null}
            <div className={styles.list}>
              {items.map((item) => {
                const Icon = icons[item.href] || FileText;
                const active = item.href === activeHref;
                return (
                  <Link
                    aria-current={active ? "page" : undefined}
                    aria-label={item.label}
                    className={`${styles.link} ${active ? styles.active : ""}`}
                    href={item.href}
                    key={item.href}
                    onClick={rememberSidebarPosition}
                    title={item.label}
                  >
                    <span className={styles.icon} aria-hidden="true"><Icon size={17} strokeWidth={1.9} /></span>
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </section>
        );
      })}
    </nav>
  );
}
