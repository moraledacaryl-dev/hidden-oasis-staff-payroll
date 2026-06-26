import { redirect } from "next/navigation";
import { BackupManager } from "@/components/BackupManager";
import { Shell } from "@/components/Shell";
import { currentSession } from "@/lib/session";

export default async function BackupPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner") return <Shell allowedRoles={["owner"]}><div /></Shell>;

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page">
        <header className="page-header">
          <div>
            <span className="eyebrow">System</span>
            <h1>Backups</h1>
          </div>
        </header>
        <section className="card">
          <BackupManager />
        </section>
      </div>
    </Shell>
  );
}
