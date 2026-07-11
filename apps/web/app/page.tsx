import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getAttendanceExceptions, getAttendanceReviews, getEmployees, getMeta, getPayrollPreview, peso } from "@/lib/api";
import { currentCutoff } from "@/lib/period";
import { currentSession } from "@/lib/session";
import type { AttendanceException, AttendanceReview } from "@/lib/api";
import type { PayrollPreview } from "@/lib/types";
import styles from "./dashboard.module.css";

function Kpi({ code, label, value, foot, trend, warning = false }: { code: string; label: string; value: string | number; foot: string; trend?: string; warning?: boolean }) {
  return <section className={`card ${styles.kpiCard}`}><div className={styles.kpiTop}><span className={styles.kpiIcon}>{code}</span>{trend ? <StatusBadge label={trend} tone={warning ? "warning" : "ok"} /> : null}</div><div className={styles.kpiLabel}>{label}</div><div className={styles.kpiValue}>{value}</div><div className={styles.kpiFoot}>{foot}</div></section>;
}

function Quick({ href, code, label, detail }: { href: string; code: string; label: string; detail: string }) {
  return <Link className={styles.quick} href={href}><span className={styles.qicon}>{code}</span><span><strong>{label}</strong><span>{detail}</span></span></Link>;
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
  const openCount = preview ? preview.checks.length : exceptions.length;
  const readiness = Math.max(0, Math.min(100, 100 - blockers * 15 - warnings * 4 - (!preview ? Math.min(openCount, 10) * 3 : 0)));

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className={`page ${styles.dashboardPage}`}>
        <header className={styles.pageHeading}>
          <div><span className="eyebrow">Command center</span><h1>Good evening, {session.display_name.split(" ")[0]}.</h1><p>{canSeePayroll ? `Your ${periodStart} to ${periodEnd} payroll is nearly ready. ${openCount} item${openCount === 1 ? "" : "s"} need review.` : "Today’s staffing, attendance, and people actions in one place."}</p></div>
          <div className={styles.headingActions}><Link className="button secondary" href={canSeePayroll ? "/cutoff" : "/attendance"}>{periodStart} to {periodEnd}</Link><Link className="button" href={canSeePayroll ? "/cutoff" : "/attendance"}>{canSeePayroll ? "Open cutoff" : "Review attendance"}</Link></div>
        </header>

        <section className={styles.heroCard}>
          <div className={styles.heroCopy}><span className="eyebrow">{canSeePayroll ? "Payroll readiness" : "Operations pulse"}</span><h2>{openCount ? `${openCount} ${canSeePayroll ? "payroll" : "operations"} item${openCount === 1 ? "" : "s"} still need a decision.` : "No blocking items remain."}</h2><p>{canSeePayroll ? "Rest days and exact matches are already cleared. Remaining items are material variances, missing logs, or deductions that require a human decision." : "Only meaningful schedule, attendance, and people exceptions remain in the queue."}</p><div className={styles.heroActions}><Link className="button" href={canSeePayroll ? "/attendance" : "/schedule/requests"}>Review now →</Link><Link className="button secondary" href="/schedule">View schedule</Link></div></div>
          <div className={styles.readiness}><div className={styles.progressRing} style={{ "--progress": readiness } as React.CSSProperties}><strong>{readiness}%</strong></div><p>{canSeePayroll ? "Cutoff readiness" : "Operations readiness"}</p></div>
        </section>

        <section className={styles.metrics}>
          <Kpi code="ST" label="Active staff" value={activeEmployees} foot={`${meta.employee_count} employee records`} />
          {preview ? <Kpi code="GR" label="Projected gross" value={peso(preview.totals.gross_pay)} foot={`${periodStart} to ${periodEnd}`} /> : <Kpi code="ON" label="Open issues" value={exceptions.length} foot="Attendance exceptions" trend={exceptions.length ? "Needs review" : "Clear"} warning={exceptions.length > 0} />}
          {preview ? <Kpi code="NT" label="Projected net" value={peso(preview.totals.net_pay)} foot="After current deductions" trend={preview.mode} warning /> : <Kpi code="ML" label="Missing logs" value={missing} foot="Incomplete time records" trend={missing ? "Review" : "Clear"} warning={missing > 0} />}
          {preview ? <Kpi code="RV" label="Items to review" value={openCount} foot={`${blockers} blockers · ${warnings} warnings`} trend={openCount ? "Needs action" : "Clear"} warning={openCount > 0} /> : <Kpi code="OT" label="Pending overtime" value={otPending} foot={`${absent} absent`} trend={otPending ? "Review" : "Clear"} warning={otPending > 0} />}
        </section>

        <section className={styles.twoCol}>
          <div className={`card ${styles.cardPad}`}>
            <div className={styles.cardHead}><div><h2>{canSeePayroll ? "Priority review queue" : "Today’s action queue"}</h2><p>Only items that require a decision are shown.</p></div><Link href={canSeePayroll ? "/attendance" : "/schedule/requests"}>View all →</Link></div>
            <div className={styles.queue}>
              {preview ? (
                preview.checks.length ? preview.checks.slice(0, 4).map((check, index) => (
                  <div className={styles.queueItem} key={`${check.category}-${index}`}>
                    <span className={`${styles.queueIcon} ${check.severity === "Blocker" ? styles.danger : ""}`}>{check.severity === "Blocker" ? "!" : "?"}</span>
                    <div><strong>{check.category}</strong><p>{check.issue}</p></div>
                    <StatusBadge label={check.severity} tone={check.severity === "Blocker" ? "danger" : "warning"} />
                  </div>
                )) : <div className="empty-state"><strong>No open items</strong><span>The review queue is clear.</span></div>
              ) : (
                exceptions.length ? exceptions.slice(0, 4).map((exception) => (
                  <div className={styles.queueItem} key={exception.id}>
                    <span className={`${styles.queueIcon} ${exception.is_absent ? styles.danger : ""}`}>{exception.is_absent ? "!" : "?"}</span>
                    <div><strong>{exception.full_name}</strong><p>{exception.work_date} · {exception.attendance_status}</p></div>
                    <StatusBadge label={exception.is_absent ? "Absent" : "Review"} tone={exception.is_absent ? "danger" : "warning"} />
                  </div>
                )) : <div className="empty-state"><strong>No open items</strong><span>The review queue is clear.</span></div>
              )}
            </div>
          </div>

          <aside className={`card ${styles.cardPad}`}><div className={styles.cardHead}><div><h2>Quick actions</h2><p>Common management tasks.</p></div></div><div className={styles.quickGrid}><Quick href="/schedule" code="+" label="Add shift" detail="Schedule staff" /><Quick href="/schedule/import" code="UP" label="Upload logs" detail="Import attendance" /><Quick href="/staff/manage" code="ST" label="Add employee" detail="Create record" /><Quick href="/cash-advances" code="CA" label="Cash advance" detail="Review request" /></div></aside>
        </section>

        <section className={styles.lowerGrid}>
          <div className={`card ${styles.cardPad}`}><div className={styles.cardHead}><div><h2>Workforce snapshot</h2><p>Current employee status.</p></div><Link href="/staff">Open staff →</Link></div><div className={styles.summaryList}><div className={styles.summaryRow}><span>Active employees</span><strong>{activeEmployees}</strong></div><div className={styles.summaryRow}><span>Inactive or terminated</span><strong>{Math.max(meta.employee_count - activeEmployees, 0)}</strong></div><div className={styles.summaryRow}><span>Reviewed attendance items</span><strong>{reviews.length}</strong></div><div className={styles.summaryRow}><span>Open attendance exceptions</span><strong>{exceptions.length}</strong></div></div></div>
          <div className={`card ${styles.cardPad}`}><div className={styles.cardHead}><div><h2>{canSeePayroll ? "Payroll movement" : "People pulse"}</h2><p>{canSeePayroll ? "Current cutoff position." : "Current attendance position."}</p></div></div><div className={styles.barChart}>{[48,62,58,72,68,Math.max(20,readiness)].map((height,index)=><div className={styles.bar} key={index} style={{height:`${height}%`}}><span>{["Apr 2","May 1","May 2","Jun 1","Jun 2","Current"][index]}</span></div>)}</div></div>
        </section>
      </div>
    </Shell>
  );
}
