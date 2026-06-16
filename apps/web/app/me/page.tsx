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
            <p className="muted">Personal staff portal shell. This is read-only until employee-specific auth is connected.</p>
          </div>
          <StatusBadge label="staff shell" tone="warning" />
        </header>

        <section className="grid cols-3">
          <div className="card"><strong>My schedule</strong><p className="muted">Upcoming shifts will appear here after the employee identity link is added.</p></div>
          <div className="card"><strong>My payslips</strong><p className="muted">Payslip access stays disabled until secure employee login is connected.</p></div>
          <div className="card"><strong>My requests</strong><p className="muted">Leave, correction, and cash advance requests will be added as audited write workflows.</p></div>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>What is active now</h2><p className="muted">This page confirms the future staff experience without exposing payroll writes.</p></div></div>
          <div className="action-list">
            <div className="action-item"><strong>Role-based navigation</strong><p className="muted">Staff users only see their own portal route.</p></div>
            <div className="action-item"><strong>No private payroll data yet</strong><p className="muted">Employee-specific payslips require real backend authentication first.</p></div>
            <div className="action-item"><strong>No request submission yet</strong><p className="muted">Writes need API permissions and audit logs before activation.</p></div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
