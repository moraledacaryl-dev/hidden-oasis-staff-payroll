import Link from "next/link";
import { navItems, roleLabels } from "@/lib/navigation";
import type { RoleKey } from "@/lib/types";

export function Shell({ children, role = "owner" }: { children: React.ReactNode; role?: RoleKey }) {
  const visibleItems = navItems.filter((item) => item.roles.includes(role));
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">HO</div>
          <div>
            <div className="brand-title">Hidden Oasis Staff Payroll</div>
            <div className="brand-subtitle">Production web shell · {roleLabels[role]}</div>
          </div>
        </div>
        <nav className="nav-list" aria-label="Main navigation">
          {visibleItems.map((item) => (
            <Link className="nav-card" href={item.href} key={item.href}>
              <strong>{item.label}</strong>
              <span>{item.description}</span>
            </Link>
          ))}
        </nav>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
