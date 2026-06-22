"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navGroups } from "@/lib/navigation";
import type { RoleKey } from "@/lib/types";
import styles from "./SidebarNav.module.css";

const glyphs: Record<string, string> = {
  "/": "DB",
  "/me": "ME",
  "/schedule": "SC",
  "/attendance": "AT",
  "/staff": "ST",
  "/performance-reviews": "PF",
  "/hr": "HR",
  "/cash-advances": "CA",
  "/cutoff": "CO",
  "/payroll": "PV",
  "/payroll/runs": "PR",
  "/payslips": "PS",
  "/reports/operations": "RO",
  "/reports": "RP",
  "/controls": "CT",
  "/backup": "BK",
  "/settings": "SE",
  "/settings/password": "AC",
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

function NavLink({ href, label, description, active, subcard = false }: {
  href: string;
  label: string;
  description: string;
  active: boolean;
  subcard?: boolean;
}) {
  return (
    <Link
      className={`nav-card ${styles.link} ${subcard ? styles.subcard : ""} ${active ? styles.activeLink : ""}`}
      href={href}
      title={label}
      aria-current={active ? "page" : undefined}
    >
      <span className={styles.glyph} aria-hidden="true">{glyphs[href] || label.slice(0, 2).toUpperCase()}</span>
      <span className={styles.copy}>
        <strong>{label}</strong>
        <small>{description}</small>
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
                  description={item.description}
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
                  description={item.description}
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
