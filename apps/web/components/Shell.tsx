import Link from "next/link";
import { redirect } from "next/navigation";
import { LogoutButton } from "@/components/LogoutButton";
import { ImpersonationBanner } from "@/components/ImpersonationBanner";
import { PasswordReminderDialog } from "@/components/PasswordReminderDialog";
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

function AppLinks() {
  const apps = [
    { label: "Operations", href: process.env.NEXT_PUBLIC_OPERATIONS_APP_URL },
    { label: "POS", href: process.env.NEXT_PUBLIC_POS_APP_URL },
    { label: "Accounting", href: process.env.NEXT_PUBLIC_ACCOUNTING_APP_URL },
  ].filter((item): item is { label: string; href: string } => Boolean(item.href));

  if (!apps.length) return null;

  return (
    <div className="grid" style={{ gap: 6, marginBottom: 10 }}>
      <span className="eyebrow">Other apps</span>
      <div className="badge-row">
        {apps.map((app) => (
          <a className="primary-link" href={app.href} key={app.label} rel="noreferrer">
            {app.label}
          </a>
        ))}
      </div>
    </div>
  );
}

export async function Shell({
  children,
  allowedRoles = ["owner"],
  allowAccountSetup = false,
}: {
  children: React.ReactNode;
  allowedRoles?: RoleKey[];
  allowAccountSetup?: boolean;
}) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!session.is_impersonating && !allowAccountSetup && session.mfa_setup_required) redirect("/settings/security");

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
        <div className={`sidebar-footer ${styles.footer}`}><AppLinks /><LogoutButton /></div>
      </aside>
      <main className="main">
        {session.is_impersonating ? <ImpersonationBanner targetName={session.display_name} targetRole={roleLabels[role]} /> : null}
        {!session.is_impersonating && !allowAccountSetup && session.must_change_password ? <PasswordReminderDialog userId={session.id} /> : null}
        {allowed ? children : <AccessRestricted role={role} allowedRoles={allowedRoles} />}
      </main>
    </div>
  );
}
