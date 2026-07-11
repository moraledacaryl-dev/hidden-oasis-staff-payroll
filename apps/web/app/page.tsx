import Link from "next/link";
import { redirect } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getAttendanceReviews, getEmployees, getMeta, getPayrollPreview, peso } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";
import type { AttendanceException, AttendanceReview } from "@/lib/api";
import type { PayrollPreview } from "@/lib/types";
import styles from "./dashboard.module.css";

function QuickLink({ href, code, label, detail }: { href: string; code: string; label: string; detail: string }) {
  return (
    <Link className={styles.quickLink} href={href}>
      <span className={styles.quickIcon} aria-hidden="true">{code}</span>
      <span className={styles.quickCopy}><strong>{label}</strong><span>{detail}</span></span>
      <span className={styles.quickArrow} aria-hidden="true">›</span>
    </Link>
  );
}

export default async function DashboardPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;

  const { periodStart, periodEnd } = currentCutoff();
  const canSeePayroll = session.role_key === "owner" || session.role_key === "payroll";
  const [meta, employees] = await Promise.all([getMeta(), getEmployees()]);
  let preview: PayrollPreview | null = null;
  let exceptions: AttendanceException[] = [];
  let reviews: AttendanceReview[] = [];

  if (canSeePayroll) preview = await getPayrollPreview(periodStart, periodEnd);
  else [exceptions, reviews] = await Promise.all([getAttendanceExceptions(periodStart, periodEnd), getAttendanceReviews(periodStart, periodEnd)]);

  const activeEmployees = employees.filter((employee) => employee.status !== "Inactive" && employee.status !== "Terminated").length;
  const blockers = preview?.checks.filter((check) => check.severity === "Blocker").length || 0;
  const warnings = preview?.checks.filter((check) => check.severity === "Warning").length || 0;
  const missing = exceptions.filter((item) => !item.actual_in || !item.actual_out).length;
  const absent = exceptions.filter((item) => item.is_absent).length;
  const otPending = exceptions.filter((item) => item.ot_status === "Pending").length;
  const queueEmpty = preview ? preview.checks.length === 0 : exceptions.length === 0;

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className={`page ${styles.dashboardPage}`}>
        <section className={styles.hero}>
          <div className={styles.heroCopy}>
            <span className="eyebrow">Command center</span>
            <h1>{canSeePayroll ? "Payroll overview" : "Operations overview"}</h1>
            <p>{canSeePayroll ? "Review the current cutoff, resolve blockers, and move payroll forward with confidence." : "Monitor attendance, schedule coverage, and team actions that need attention."}</p>
          </div>
          <div className={styles.heroStatus}>
            <div className="badge-row"><StatusBadge label="Connected" />{preview ? <StatusBadge label={preview.mode} tone="warning" /> : <StatusBadge label="Operations" tone="warning" />}</div>
            <div className={styles.periodPill}>{periodStart} to {periodEnd}</div>
          </div>
        </section>

        <section className={styles.metrics}>
          <MetricCard label="Active staff" value={activeEmployees} detail={`${meta.employee_count} total records`} />
          {preview ? <MetricCard label="Gross payroll" value={peso(preview.totals.gross_pay)} detail="Current preview" /> : <MetricCard label="Open issues" value={exceptions.length} detail="Attendance exceptions" />}
          {preview ? <MetricCard label="Net payroll" value={peso(preview.totals.net_pay)} detail="Current preview" /> : <MetricCard label="Missing logs" value={missing} detail="Incomplete time entries" />}
          {preview ? <MetricCard label="Deductions" value={peso(preview.totals.total_deductions)} detail="Current preview" /> : <MetricCard label="OT pending" value={otPending} detail={`${absent} absent`} />}
        </section>

        <section className={styles.contentGrid}>
          <div className={`card ${styles.queueCard}`}>
            <div className={styles.queueHeader}>
              <div>
                <span className="eyebrow">Priority queue</span>
                <h2>{canSeePayroll ? "Cutoff readiness" : "Attendance action list"}</h2>
                <p className="muted">{canSeePayroll ? "Clear these items before approval and payment." : "Review attendance items that still need a decision."}</p>
              </div>
              {canSeePayroll ? <div className="badge-row"><StatusBadge label={`${blockers} blockers`} tone={blockers ? "danger" : "ok"} /><StatusBadge label={`${warnings} warnings`} tone={warnings ? "warning" : "ok"} /></div> : <StatusBadge label={`${reviews.length} reviewed`} />}
            </div>

            {queueEmpty ? <div className={styles.emptyQueue}><div><strong>No open items</strong><p>The current queue is clear.</p></div></div> : null}

            <div className={styles.queueList}>
              {preview ? preview.checks.slice(0, 6).map((check, index) => (
                <div className={styles.queueItem} key={`${check.category}-${index}`}>
                  <span className={`${styles.queueRail} ${check.severity === "Blocker" ? styles.queueRailDanger : ""}`} aria-hidden="true" />
                  <div className={styles.queueCopy}><strong>{check.category}</strong><p>{check.issue}</p><p>{check.recommended_action}</p></div>
                  <StatusBadge label={check.severity} tone={check.severity === "Blocker" ? "danger" : "warning"} />
                </div>
              )) : exceptions.slice(0, 6).map((item) => (
                <div className={styles.queueItem} key={item.id}>
                  <span className={`${styles.queueRail} ${item.is_absent ? styles.queueRailDanger : styles.queueRailOk}`} aria-hidden="true" />
                  <div className={styles.queueCopy}><strong>{item.full_name}</strong><p>{item.work_date} · {item.attendance_status}</p><p>{item.actual_in || "—"} / {item.actual_out || "—"}</p></div>
                  <StatusBadge label={item.is_absent ? "Absent" : "Review"} tone={item.is_absent ? "danger" : "warning"} />
                </div>
              ))}
            </div>
          </div>

          <aside className={`card ${styles.quickCard}`}>
            <div className={styles.quickHeader}><span className="eyebrow">Navigate</span><h2>Quick actions</h2><p className="muted">Open the most-used workspaces.</p></div>
            <div className={styles.quickActions}>
              <QuickLink href="/schedule" code="SC" label="Schedule" detail="Plan and review shifts" />
              <QuickLink href="/attendance" code="AT" label="Attendance" detail="Review logs and exceptions" />
              {session.role_key === "supervisor" ? <QuickLink href="/performance-reviews" code="PR" label="Performance reviews" detail="Open employee reviews" /> : <QuickLink href="/payroll/runs" code="PY" label="Payroll runs" detail="Review payroll lifecycle" />}
              {session.role_key === "supervisor" ? <QuickLink href="/cash-advances" code="CA" label="Cash advances" detail="Review staff requests" /> : <QuickLink href="/hr" code="HR" label="HR records" detail="Open employee records" />}
              <QuickLink href={session.role_key === "supervisor" ? "/reports/operations" : "/reports"} code="RP" label="Reports" detail="Review operational results" />
              <QuickLink href="/settings/password" code="AC" label="Account" detail="Security and password" />
            </div>
          </aside>
        </section>
      </div>
    </Shell>
  );
}
