"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navGroups } from "@/lib/navigation";
import type { RoleKey } from "@/lib/types";

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SidebarNav({ role }: { role: RoleKey }) {
  const pathname = usePathname();

  return (
    <nav className="nav-list" aria-label="Main navigation">
      {navGroups.map((group) => {
        const items = group.items.filter((item) => item.roles.includes(role));
        if (!items.length) return null;

        const groupActive = items.some((item) => isActive(pathname, item.href));

        if (!group.label) {
          return items.map((item) => (
            <Link
              className={`nav-card ${isActive(pathname, item.href) ? "active" : ""}`}
              href={item.href}
              key={item.href}
              title={item.label}
            >
              <strong>{item.label}</strong>
              <span>{item.description}</span>
            </Link>
          ));
        }

        return (
          <details className="nav-group" defaultOpen={groupActive} key={group.label}>
            <summary className={groupActive ? "active" : ""}>
              <strong>{group.label}</strong>
              <span className="nav-chevron" aria-hidden="true">›</span>
            </summary>
            <div className="nav-sublist">
              {items.map((item) => (
                <Link
                  className={`nav-card nav-subcard ${isActive(pathname, item.href) ? "active" : ""}`}
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
