"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navGroups } from "@/lib/navigation";
import type { RoleKey } from "@/lib/types";
import styles from "./SidebarNav.module.css";

function routeMatches(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function activeHrefFor(pathname: string, hrefs: string[]): string | null {
  return hrefs
    .filter((href) => routeMatches(pathname, href))
    .sort((a, b) => b.length - a.length)[0] || null;
}

export function SidebarNav({ role }: { role: RoleKey }) {
  const pathname = usePathname();
  const visibleHrefs = navGroups
    .flatMap((group) => group.items)
    .filter((item) => item.roles.includes(role))
    .map((item) => item.href);
  const activeHref = activeHrefFor(pathname, visibleHrefs);

  return (
    <nav className="nav-list" aria-label="Main navigation">
      {navGroups.map((group, groupIndex) => {
        const items = group.items.filter((item) => item.roles.includes(role));
        if (!items.length) return null;

        const groupActive = items.some((item) => item.href === activeHref);

        if (!group.label) {
          return items.map((item) => (
            <Link
              className={`nav-card ${item.href === activeHref ? styles.activeLink : ""}`}
              href={item.href}
              key={`${groupIndex}-${item.href}`}
              title={item.label}
            >
              <strong>{item.label}</strong>
              <span>{item.description}</span>
            </Link>
          ));
        }

        return (
          <details
            className={styles.group}
            open={groupActive || undefined}
            key={`${group.label}-${pathname}`}
          >
            <summary className={groupActive ? styles.active : ""}>
              <strong>{group.label}</strong>
              <span className={styles.chevron} aria-hidden="true">›</span>
            </summary>
            <div className={styles.sublist}>
              {items.map((item) => (
                <Link
                  className={`nav-card ${styles.subcard} ${item.href === activeHref ? styles.activeLink : ""}`}
                  href={item.href}
                  key={item.href}
                  title={item.label}
                >
                  <strong>{item.label}</strong>
                  <span>{item.description}</span>
                </Link>
              ))}
            </div>
          </details>
        );
      })}
    </nav>
  );
}
