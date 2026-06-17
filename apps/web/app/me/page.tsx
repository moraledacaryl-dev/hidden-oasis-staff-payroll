import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { currentName } from "@/lib/session";

export default async function MyPortalPage() {
  const name = await currentName();

  return (
    <Shell allowedRoles={["staff"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">My Portal</span>
            <h1>Hi, {name}.</h1>
            <p className="muted">Your schedule, payslips, and requests.</p>
          </div>
          <StatusBadge label="staff" tone="warning" />
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>My schedule</strong><p className="muted">Coming next.</p></div>
          <div className="card"><strong>My payslips</strong><p className="muted">Coming next.</p></div>
          <div className="card"><strong>My requests</strong><p className="muted">Coming next.</p></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Access</h2><p className="muted">Staff route only.</p></div></div>
          <div className="action-list">
            <div className="action-item"><strong>Private payroll</strong><p className="muted">Hidden until employee identity is linked.</p></div>
            <div className="action-item"><strong>Requests</strong><p className="muted">Will use audited approvals.</p></div>
            <div className="action-item"><strong>Navigation</strong><p className="muted">Limited by role.</p></div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
