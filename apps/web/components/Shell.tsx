import Link from "next/link";
import { redirect } from "next/navigation";
import { LogoutButton } from "@/components/LogoutButton";
import { SidebarNav } from "@/components/SidebarNav";
import { SidebarToggle } from "@/components/SidebarToggle";
import { roleLabels } from "@/lib/navigation";
import { currentSession } from "@/lib/session";
import type { RoleKey } from "@/lib/types";
import styles from "./SidebarChrome.module.css";

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
  const allowed = allowedRoles.includes(role);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${styles.sidebar}`}>
        <div className={`brand ${styles.brand}`}>
          <div className={`brand-mark ${styles.brandMark}`}>HO</div>
          <div className={`brand-text ${styles.brandText}`}>
            <div className="brand-title">Hidden Oasis</div>
            <div className="brand-subtitle">{session.display_name} · {roleLabels[role]}</div>
          </div>
          <SidebarToggle />
        </div>
        <SidebarNav role={role} />
        <div className={`sidebar-footer ${styles.footer}`}><LogoutButton /></div>
      </aside>
      <main className="main">{allowed ? children : <AccessRestricted role={role} allowedRoles={allowedRoles} />}</main>
    </div>
  );
}
