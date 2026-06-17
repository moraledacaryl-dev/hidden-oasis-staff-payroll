import Link from "next/link";
import { redirect } from "next/navigation";
import { LogoutButton } from "@/components/LogoutButton";
import { SidebarToggle } from "@/components/SidebarToggle";
import { navItems, roleLabels } from "@/lib/navigation";
import { currentSession } from "@/lib/session";
import type { RoleKey } from "@/lib/types";

function AccessRestricted({ role, allowedRoles }: { role: RoleKey; allowedRoles: RoleKey[] }) {
  return (
    <div className="page">
      <section className="card">
        <span className="eyebrow">Access restricted</span>
        <h1>This workspace is not for {roleLabels[role]}.</h1>
        <p className="muted">Allowed roles: {allowedRoles.map((allowed) => roleLabels[allowed]).join(", ")}.</p>
        <div className="badge-row"><Link className="primary-link" href="/">Go to command center</Link></div>
      </section>
    </div>
  );
}

export async function Shell({ children, allowedRoles = ["owner"] }: { children: React.ReactNode; allowedRoles?: RoleKey[] }) {
  const session = await currentSession();
  if (!session) redirect("/login");

  const role = session.role_key;
  const visibleItems = navItems.filter((item) => item.roles.includes(role));
  const allowed = allowedRoles.includes(role);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">HO</div><div className="brand-text"><div className="brand-title">Hidden Oasis</div><div className="brand-subtitle">{session.display_name} · {roleLabels[role]}</div></div><SidebarToggle /></div>
        <nav className="nav-list" aria-label="Main navigation">{visibleItems.map((item) => (<Link className="nav-card" href={item.href} key={item.href} title={item.label}><strong>{item.label}</strong><span>{item.description}</span></Link>))}</nav>
        <div className="sidebar-footer"><LogoutButton /></div>
      </aside>
      <main className="main">{allowed ? children : <AccessRestricted role={role} allowedRoles={allowedRoles} />}</main>
    </div>
  );
}
