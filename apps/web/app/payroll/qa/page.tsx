import Link from "next/link";
import { redirect } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge, severityTone } from "@/components/StatusBadge";
import { getPayrollQa, type PayrollQaRow } from "@/lib/api";
import { currentCutoff, mondayOfWeek } from "@/lib/period";
import { currentSession } from "@/lib/session";

function displayTime(value?: string | null) {
  return value ? String(value).slice(0, 5) : "—";
}

function scheduleText(row: PayrollQaRow) {
  if (!row.schedule) return "No schedule";
  return `${displayTime(row.schedule.start_time)}–${displayTime(row.schedule.end_time)}`;
}

function actualText(row: PayrollQaRow) {
  if (!row.actual) return "No manual actual";
  if (row.actual.is_absent) return row.actual.absence_type || "Absent";
  return `${displayTime(row.actual.actual_in)}–${displayTime(row.actual.actual_out)}`;
}

function biometricText(row: PayrollQaRow) {
  if (!row.biometric) return "No biometric";
  return `${displayTime(row.biometric.actual_in)}–${displayTime(row.biometric.actual_out)}`;
}

function rowAction(row: PayrollQaRow) {
  const first = row.flags[0]?.code || "";
  if (first === "SCHEDULED_NO_ATTENDANCE") return "Review absence";
  if (first === "BIOMETRIC_WITHOUT_MANUAL") return "Create/ignore actual";
  if (first === "ACTUAL_WITHOUT_SCHEDULE") return "Fix schedule";
  if (first === "HALFDAY_REMARK" || first === "HALFDAY_CANDIDATE") return "Approve halfday";
  if (first === "EARLY_OUT") return "Review early out";
  if (first === "OT_CANDIDATE") return "Approve/reject OT";
  if (first === "MISSING_TIME_OUT") return "Fill time-out";
  return "Review";
}

function flagSummary(row: PayrollQaRow) {
  return row.flags.map((flag) => flag.label).join("; ");
}

export default async function PayrollQaPage({ searchParams }: { searchParams: Promise<{ period_start?: string; period_end?: string; include_info?: string; severity?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") {
    return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  }
  const params = await searchParams;
  const cutoff = currentCutoff();
  const periodStart = params.period_start || cutoff.periodStart;
  const periodEnd = params.period_end || cutoff.periodEnd;
  const includeInfo = params.include_info === "1" || params.include_info === "true";
  const severity = params.severity || "all";
  const qa = await getPayrollQa(periodStart, periodEnd, includeInfo);
  const rows = qa.items.filter((item) => severity === "all" || item.severity === severity);

  function qaHref(next: Record<string, string | undefined>) {
    const query = new URLSearchParams();
    query.set("period_start", next.period_start || periodStart);
    query.set("period_end", next.period_end || periodEnd);
    if ((next.include_info || (includeInfo ? "1" : "")) === "1") query.set("include_info", "1");
    const nextSeverity = next.severity || severity;
    if (nextSeverity !== "all") query.set("severity", nextSeverity);
    return `/payroll/qa?${query.toString()}`;
  }

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Payroll QA</span>
            <h1>Attendance actions</h1>
            <p className="muted">Schedule vs actual vs biometric flags before payroll approval.</p>
          </div>
          <div className="badge-row">
            <StatusBadge label={`${qa.period_start} to ${qa.period_end}`} tone="warning" />
            <StatusBadge label={qa.mode} tone="warning" />
          </div>
        </header>

        <section className="grid cols-4">
          <MetricCard label="Critical" value={qa.totals.critical} />
          <MetricCard label="Warnings" value={qa.totals.warning} />
          <MetricCard label="Info" value={qa.totals.info} />
          <MetricCard label="Rows" value={qa.totals.rows} />
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Cutoff</h2>
              <p className="muted">Change the period or include info rows like manual-only attendance.</p>
            </div>
            <div className="badge-row">
              <Link className="primary-link" href="/payroll">Payroll preview</Link>
              <Link className="primary-link" href="/schedule/import">Attendance upload</Link>
            </div>
          </div>
          <form className="grid cols-4" action="/payroll/qa">
            <label className="grid" style={{ gap: 6 }}>
              <strong>Period start</strong>
              <input name="period_start" type="date" defaultValue={periodStart} />
            </label>
            <label className="grid" style={{ gap: 6 }}>
              <strong>Period end</strong>
              <input name="period_end" type="date" defaultValue={periodEnd} />
            </label>
            <label className="grid" style={{ gap: 6 }}>
              <strong>Severity</strong>
              <select name="severity" defaultValue={severity}>
                <option value="all">All</option>
                <option value="critical">Critical</option>
                <option value="warning">Warning</option>
                <option value="info">Info</option>
              </select>
            </label>
            <label className="grid" style={{ gap: 6 }}>
              <strong>Info rows</strong>
              <select name="include_info" defaultValue={includeInfo ? "1" : "0"}>
                <option value="0">Hide rest/no-data info</option>
                <option value="1">Include info rows</option>
              </select>
            </label>
            <button className="primary-link" type="submit">Run QA</button>
          </form>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Flags</h2>
              <p className="muted">Approve, correct, mark absence, mark halfday, or handle biometric-only rows from the schedule view.</p>
            </div>
            <div className="badge-row">
              <Link className="primary-link" href={qaHref({ severity: "critical" })}>Critical</Link>
              <Link className="primary-link" href={qaHref({ severity: "warning" })}>Warnings</Link>
              <Link className="primary-link" href={qaHref({ severity: "all" })}>All</Link>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Employee</th>
                  <th>Schedule</th>
                  <th>Actual</th>
                  <th>Biometric</th>
                  <th>Flags</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.employee_id}-${row.work_date}-${row.flags.map((flag) => flag.code).join("-")}`}>
                    <td><strong>{row.work_date}</strong></td>
                    <td><strong>{row.employee_name}</strong><br /><span className="muted">{row.employee_code || "—"} · {row.department || "—"}</span></td>
                    <td>{scheduleText(row)}<br /><span className="muted">{row.schedule_count ? `${row.schedule_count} schedule row(s)` : "—"}</span></td>
                    <td>{actualText(row)}<br /><span className="muted">{row.actual?.attendance_status || row.actual?.source || "—"}</span></td>
                    <td>{biometricText(row)}<br /><span className="muted">{row.biometric_log_count ? `${row.biometric_log_count} biometric row(s)` : "—"}</span></td>
                    <td>
                      <div className="badge-row">{row.flags.slice(0, 3).map((flag) => <StatusBadge key={flag.code} label={flag.code} tone={severityTone(flag.severity)} />)}</div>
                      <p className="muted">{flagSummary(row)}</p>
                    </td>
                    <td>
                      <Link className="primary-link" href={`/schedule?week_start=${mondayOfWeek(row.work_date)}&employee_id=${row.employee_id}`}>{rowAction(row)}</Link>
                      <p className="muted">Open schedule + actual review.</p>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 ? <tr><td colSpan={7}>No QA rows for this filter.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
