import Link from "next/link";
import { redirect } from "next/navigation";
import { LogoutButton } from "@/components/LogoutButton";
import { ImpersonationBanner } from "@/components/ImpersonationBanner";
import { MobileSidebarOverlay } from "@/components/MobileSidebarOverlay";
import { PasswordReminderDialog } from "@/components/PasswordReminderDialog";
import { SidebarCollapseController } from "@/components/SidebarCollapseController";
import { SidebarNav } from "@/components/SidebarNav";
import { WorkspaceChrome } from "@/components/WorkspaceChrome";
import { roleLabels } from "@/lib/navigation";
import { currentSession } from "@/lib/session";
import type { RoleKey } from "@/lib/types";
import styles from "./PrototypeShell.module.css";

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "HO";
}

function AccessRestricted({ role, allowedRoles }: { role: RoleKey; allowedRoles: RoleKey[] }) {
  return (
    <div className={styles.restricted}>
      <section className={styles.restrictedCard}>
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
    process.env.NEXT_PUBLIC_OPERATIONS_APP_URL
      ? { label: "Operations", href: process.env.NEXT_PUBLIC_OPERATIONS_APP_URL }
      : null,
    {
      label: "Accounting",
      href: process.env.NEXT_PUBLIC_ACCOUNTING_APP_URL || "https://hiddenoasis.app",
    },
    {
      label: "POS",
      href: process.env.NEXT_PUBLIC_POS_APP_URL || "https://pos.hiddenoasis.app",
    },
    {
      label: "Inventory",
      href: process.env.NEXT_PUBLIC_INVENTORY_APP_URL || "https://inventory.hiddenoasis.app",
    },
  ].filter((app): app is { label: string; href: string } => Boolean(app?.href));

  return (
    <div className={styles.appLinks} aria-label="Hidden Oasis applications">
      {apps.map((app) => (
        <a
          aria-label={`Open ${app.label}`}
          className={styles.appPill}
          href={app.href}
          key={app.label}
          rel="noreferrer"
          title={`Open ${app.label}`}
        >
          {app.label}
        </a>
      ))}
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
    <div className={styles.app}>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <aside className={styles.sidebar} aria-label="Workspace navigation">
        <SidebarCollapseController />
        <div className={styles.brand}>
          <div className={styles.brandMark}>HO</div>
          <div className={styles.brandText}>
            <div className={styles.brandTitle}>Hidden Oasis</div>
            <div className={styles.brandSubtitle}>Staff &amp; Payroll</div>
          </div>
        </div>

        <SidebarNav role={role} />

        <div className={styles.footer}>
          <AppLinks />
          <div className={styles.profile}>
            <div className={styles.avatar}>{initials(session.display_name)}</div>
            <div className={styles.profileCopy}>
              <strong>{session.display_name}</strong>
              <span>{roleLabels[role]}</span>
            </div>
            <div className={styles.logoutWrap}><LogoutButton /></div>
          </div>
        </div>
      </aside>

      <MobileSidebarOverlay className={styles.overlay} />

      <section className={styles.shell}>
        <main className={styles.main} id="main-content" tabIndex={-1}>
          <WorkspaceChrome role={role} />
          {session.is_impersonating ? <ImpersonationBanner targetName={session.display_name} targetRole={roleLabels[role]} /> : null}
          {!session.is_impersonating && !allowAccountSetup && session.must_change_password ? <PasswordReminderDialog userId={session.id} /> : null}
          {allowed ? children : <AccessRestricted role={role} allowedRoles={allowedRoles} />}
        </main>
      </section>
    </div>
  );
}
