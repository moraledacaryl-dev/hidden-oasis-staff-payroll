import Link from "next/link";
import { redirect } from "next/navigation";
import { Building2, HeartPulse, House, ChevronDown, ReceiptText } from "lucide-react";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, PageHeading, SectionBody, SectionCard, SectionHeader } from "@/components/UiPrimitives";
import { getMonthlyBenefits, getRemittanceBalances, peso, type MonthlyBenefitItem } from "@/lib/api";
import { todayInManilaIso } from "@/lib/period";
import { currentSession } from "@/lib/session";
import { OutsideBenefitPayment } from "@/components/OutsideBenefitPayment";
import { AgencyRemittanceForm } from "@/components/AgencyRemittanceForm";
import { AgencyRemittanceHistory } from "@/components/AgencyRemittanceHistory";
import styles from "./page.module.css";

const agencies = [
  { key: "sss", name: "SSS", icon: Building2, ee: "sss_ee", er: "sss_er" },
  { key: "philhealth", name: "PhilHealth", icon: HeartPulse, ee: "philhealth_ee", er: "philhealth_er" },
  { key: "pagibig", name: "Pag-IBIG", icon: House, ee: "pagibig_ee", er: "pagibig_er" },
] as const;

function EmployeeContributions({ item, month, canRecord }: { item: MonthlyBenefitItem; month: string; canRecord: boolean }) {
  const outstanding = item.due.sss_ee + item.due.philhealth_ee + item.due.pagibig_ee;
  return <details className={styles.employee}>
    <summary>
      <span className={styles.avatar} aria-hidden="true">{item.full_name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join("")}</span>
      <span className={styles.employeeName}><strong>{item.full_name}</strong><span>{item.employee_code || "Employee"}</span></span>
      <StatusBadge label={item.status} tone={item.status === "Complete" ? "ok" : "warning"} />
      <span className={styles.employeeDue}><small>Employee due</small><strong>{peso(outstanding)}</strong></span>
      <ChevronDown size={17} className={styles.chevron} aria-hidden="true" />
    </summary>
    <div className={styles.employeeDetails}>
      <div className={styles.coverage}><span>{item.status === "Complete" ? `Covered through ${item.covered_through || "month end"}` : `Missing coverage from ${item.missing_from || "next cutoff"}`}</span><span>Gross basis <strong>{peso(item.gross_pay)}</strong></span></div>
      <div className={styles.contributions}>{agencies.map(agency => <div key={agency.key}>
        <h3>{agency.name}</h3>
        <dl><div><dt>Employee contribution</dt><dd>{peso(item[agency.ee])}</dd></div><div><dt>From paid payroll</dt><dd>{peso(item.paid[agency.ee])}</dd></div><div><dt>Employee due</dt><dd><strong>{peso(item.due[agency.ee])}</strong></dd></div><div><dt>Employer contribution</dt><dd>{peso(item[agency.er])}</dd></div>{agency.key === "sss" ? <div><dt>Employees’ compensation</dt><dd>{peso(item.sss_ec)}</dd></div> : null}</dl>
      </div>)}</div>
      <div className={styles.settlement}>
        <div><h3>Separate payments & catch-up</h3><p>Paid separately: PhilHealth {peso(item.settled_separately?.philhealth)} · Pag-IBIG {peso(item.settled_separately?.pagibig)}</p><p>Catch-up recorded: PhilHealth {peso(item.catchup?.philhealth)} · Pag-IBIG {peso(item.catchup?.pagibig)}</p></div>
        {canRecord ? <OutsideBenefitPayment employeeId={item.employee_id} employeeName={item.full_name} month={month} /> : null}
      </div>
      <div className={styles.sourceRuns}><strong>Source payroll runs</strong>{item.runs.length ? item.runs.map(run => <span key={run.run_id}>{canRecord ? <Link href={`/payroll/runs/${run.run_id}`}>Run #{run.run_id}</Link> : <span>Run #{run.run_id}</span>} · {run.period_start}–{run.period_end} · {run.status}</span>) : <span>No source runs</span>}</div>
    </div>
  </details>;
}

export default async function BenefitsPage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  const allowed = ["owner", "payroll", "supervisor"] as const;
  if (!allowed.some(role => role === session.role_key)) return <Shell allowedRoles={[...allowed]}><div /></Shell>;
  const query = await searchParams;
  const month = /^\d{4}-(0[1-9]|1[0-2])$/.test(query.month || "") ? query.month! : todayInManilaIso().slice(0, 7);
  const canRecord = session.role_key !== "supervisor";
  const [ledger, balances] = await Promise.all([getMonthlyBenefits(month), canRecord ? getRemittanceBalances(month) : Promise.resolve(null)]);
  const monthLabel = new Date(`${month}-01T00:00:00Z`).toLocaleDateString("en-PH", { month: "long", year: "numeric", timeZone: "UTC" });
  const pending = ledger.items.filter(item => item.status !== "Complete").length;
  return <Shell allowedRoles={[...allowed]}><div className={`page ${styles.page}`}>
    <PageHeading eyebrow="Payroll" title="Monthly benefits" description="Contributions, employee collections, and agency payments." actions={canRecord ? <Link className="button secondary" href="/payroll/runs">Payroll runs</Link> : undefined} />
    <div className={styles.monthBar}><form><label>Contribution month<input name="month" type="month" defaultValue={month} required /></label><button className="button" type="submit">View month</button></form><span><ReceiptText size={17} aria-hidden="true" />{monthLabel}</span></div>
    {balances ? <section aria-label="Agency balances" className={styles.agencies}>{agencies.map(agency => {
      const balance = balances.programs[agency.key]?.at(-1);
      const closing = balance?.closing_balance || 0;
      const Icon = agency.icon;
      return <article key={agency.key} className={styles.agency}>
        <header><span className={styles.agencyIcon}><Icon size={21} strokeWidth={1.6} aria-hidden="true" /></span><h2>{agency.name}</h2><StatusBadge label={closing < 0 ? "Unverified credit" : closing > 0 ? "Outstanding" : "Balanced"} tone={closing < 0 || closing > 0 ? "warning" : "ok"} /></header>
        <span className={styles.balanceLabel}>Closing balance</span><strong className={styles.balance}>{peso(closing)}</strong>
        <dl><div><dt>Opening balance</dt><dd>{peso(balance?.opening_balance)}</dd></div><div><dt>Employee due this month</dt><dd>{peso(balance?.employee_due)}</dd></div><div><dt>Employer due this month</dt><dd>{peso(balance?.employer_due)}</dd></div><div><dt>Remitted this month</dt><dd>{peso(balance?.remitted)}</dd></div></dl>
      </article>;
    })}</section> : null}
    <p className={styles.note}>Paid payroll does not confirm government remittance.{balances ? " Agency balances include employee and employer obligations from paid payroll; negative balances are unverified credits." : ""}</p>
    <SectionCard>
      <SectionHeader title="Employee contributions" description={`${monthLabel} · ${ledger.items.length} employee${ledger.items.length === 1 ? "" : "s"}`} actions={<StatusBadge label={!ledger.items.length ? "No records" : pending ? `${pending} pending coverage` : "Coverage complete"} tone={!ledger.items.length ? "neutral" : pending ? "warning" : "ok"} />} />
      <SectionBody>{ledger.items.length ? <div className={styles.employeeList}>{ledger.items.map(item => <EmployeeContributions key={item.employee_id} item={item} month={month} canRecord={canRecord} />)}</div> : <EmptyState title="No contributions recorded" description={ledger.message || "Statutory snapshots will appear as payroll is processed for this month."} />}</SectionBody>
    </SectionCard>
    {canRecord ? <SectionCard>
      <SectionHeader title="Government remittances" description="Record payments made to SSS, PhilHealth, or Pag-IBIG." />
      <SectionBody><AgencyRemittanceForm key={month} month={month} /><div className={styles.history}><h3>Recorded agency payments</h3><AgencyRemittanceHistory month={month} /></div></SectionBody>
    </SectionCard> : null}
  </div></Shell>;
}
