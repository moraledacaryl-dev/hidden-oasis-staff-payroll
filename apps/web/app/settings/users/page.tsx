import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { UserManagementClient } from "@/components/UserManagementClient";
import { getAppUsers, getEmployees } from "@/lib/api";
import { currentSession } from "@/lib/session";

export default async function UserSettingsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner") {
    return <Shell allowedRoles={["owner"]}><div /></Shell>;
  }
  const [users, employees] = await Promise.all([getAppUsers(), getEmployees()]);

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Users</span>
            <h1>User management</h1>
            <p className="muted">Owner-only app users, active state, and temporary password resets.</p>
            <div className="action-row"><Link className="button ghost" href="/settings">Settings</Link><Link className="button ghost" href="/settings/password">My password</Link></div>
          </div>
        </header>
        <section className="card">
          <UserManagementClient users={users.items} employees={employees} />
        </section>
      </div>
    </Shell>
  );
}
