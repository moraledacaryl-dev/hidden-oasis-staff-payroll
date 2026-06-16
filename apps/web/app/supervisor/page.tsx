import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getPayrollPreview, numberText } from "@/lib/api";

const DEFAULT_START = "2026-06-01";
const DEFAULT_END = "2026-06-15";

export default async function SupervisorPage() {
  const [preview, exceptions] = await Promise.all([
    getPayrollPreview(DEFAULT_START, DEFAULT_END),
    getAttendanceExceptions(DEFAULT_START, DEFAULT_END),
  ]);
  const attendanceChecks = preview.checks.filter((check) => check.category === "Attendance" || check.category === "Overtime" || check.category === "Leaves");

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Supervisor</span><h1>Daily action queue</h1><p className="muted">API-backed attendance and OT exceptions for {DEFAULT_START} to {DEFAULT_END}.</p></div><StatusBadge label="audited actions ready" tone="warning" /></header>
        <section className="grid cols-3"><div className="card"><strong>{exceptions.length} attendance exception(s)</strong><p className="muted">Missing, pending, absent, incomplete, or OT-pending logs.</p></div><div className="card"><strong>OT decisions</strong><p className="muted">Backend endpoint can approve/reject OT with reason and audit entry.</p></div><div className="card"><strong>Payroll still locked</strong><p className="muted">This does not create, approve, or pay payroll runs.</p></div></section>
        <section className="card"><div className="panel-title"><div><h2>Attendance exception queue</h2><p className="muted">Pulled from /api/v1/attendance/exceptions.</p></div></div><div className="table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>In / Out</th><th>Attendance</th><th>Detected OT</th><th>Approved OT</th><th>OT status</th></tr></thead><tbody>{exceptions.map((item) => (<tr key={item.id}><td>{item.work_date}</td><td><strong>{item.full_name}</strong><br /><span className="muted">{item.employee_code} · {item.department || "—"}</span></td><td>{item.actual_in || "—"} / {item.actual_out || "—"}</td><td>{item.is_absent ? "Absent" : item.attendance_status}</td><td>{numberText(item.detected_ot_hours)}</td><td>{numberText(item.approved_ot_hours)}</td><td>{item.ot_status || "None"}</td></tr>))}{exceptions.length === 0 ? <tr><td colSpan={7}>No attendance exceptions for this cutoff.</td></tr> : null}</tbody></table></div></section>
        <section className="card"><div className="panel-title"><div><h2>Payroll QA attendance items</h2><p className="muted">Still shown separately from payroll preflight.</p></div></div><div className="action-list">{attendanceChecks.map((check, index) => (<div className="action-item" key={`${check.category}-${index}`}><div className="badge-row"><StatusBadge label={check.severity} tone={check.severity === "Blocker" ? "danger" : "warning"} /></div><strong>{check.category}</strong><p>{check.issue}</p><p className="muted">{check.recommended_action}</p></div>))}{attendanceChecks.length === 0 ? <p className="muted">No attendance, OT, or leave QA items for this cutoff.</p> : null}</div></section>
      </div>
    </Shell>
  );
}
