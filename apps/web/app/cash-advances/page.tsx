import { MobileSection } from "@/components/MobileSection";
import Link from "next/link";
import { redirect } from "next/navigation";
import { CashAdvanceBalanceCorrection } from "@/components/CashAdvanceBalanceCorrection";
import { CashAdvanceForm } from "@/components/CashAdvanceForm";
import { ConfirmCashAdvanceRelease } from "@/components/ConfirmCashAdvanceRelease";
import { CashAdvanceCreditSettlementForm } from "@/components/CashAdvanceCreditSettlementForm";
import { ManualRepaymentForm } from "@/components/ManualRepaymentForm";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { PageHeading } from "@/components/UiPrimitives";
import { apiBaseUrl, backendHeaders, peso } from "@/lib/api";
import { currentSession } from "@/lib/session";
import "./cash-advances.css";

type Employee = { id: number; full_name: string };
type Repayment = {
  id: number;
  repayment_date: string;
  amount: number;
  source: string;
  payment_method?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  created_by?: string | null;
  accounting_handoff_state?: string | null;
  accounting_outbox_status?: string | null;
};
type Advance = {
  id: number;
  employee_id: number;
  full_name?: string;
  employee_code?: string;
  department?: string;
  advance_date: string;
  amount: number;
  ledger_opening_balance?: number | null;
  deduction_per_payroll: number;
  remaining_balance: number;
  total_repaid?: number;
  overpayment_credit?: number;
  repayment_method?: string;
  release_confirmation_required?: number | null;
  released_at?: string | null;
  release_method?: string | null;
  status: string;
  reason?: string | null;
  repayments?: Repayment[];
};

const activeStatuses = new Set(["Active", "Approved", "Partially Paid", "Released"]);

// These are Staff delivery exceptions, not proof that Accounting lacks a
// legitimate journal or that cash was received. Do not include Pending or
// Completed: those states require separate downstream posting verification.
const handoffReviewStates = new Set([
  "missing_staff_outbox",
  "delivery_requires_review",
  "outbox_status_unavailable",
]);

function needsAccountingHandoffReview(repayment: Repayment): boolean {
  return repayment.source?.trim().toLowerCase() === "manual" &&
    handoffReviewStates.has(repayment.accounting_handoff_state || "");
}

// Only Staff outbox transport is visible here. An Accounting delivery is NOT
// evidence of accepted review, posted journal, or verified cash custody.
function accountingHandoffLabel(repayment: Repayment): string | null {
  if (repayment.source?.trim().toLowerCase() !== "manual") return null;
  switch (repayment.accounting_handoff_state) {
    case "missing_staff_outbox": return "No Staff Accounting handoff";
    case "pending_delivery": return "Accounting delivery queued";
    case "delivered_posting_unverified": return "Delivered · posting unverified";
    case "delivery_requires_review":
      return `Accounting delivery needs review (${repayment.accounting_outbox_status || "Unknown"})`;
    default: return "Accounting handoff unavailable";
  }
}

async function loadAdvances(): Promise<Advance[]> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/cash-advances`, { headers: await backendHeaders(), cache: "no-store" });
  if (!response.ok) throw new Error(`Cash advances could not be loaded (${response.status}).`);
  const data = await response.json().catch(() => ({}));
  return data.items || [];
}

async function loadEmployees(): Promise<Employee[]> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/schedules/employees`, { headers: await backendHeaders(), cache: "no-store" });
  if (!response.ok) throw new Error(`Employees could not be loaded (${response.status}).`);
  const data = await response.json().catch(() => ({}));
  return data.items || [];
}

function formatDate(value: string): string {
  if (!value) return "—";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("en-PH", { month: "short", day: "numeric", year: "numeric" });
}

type CashAdvanceView = "all" | "awaiting" | "outstanding" | "closed";

function statusLabel(item: Advance): string {
  if (item.status === "Fully Paid" || item.status === "Cancelled") return item.status;
  if (Number(item.release_confirmation_required || 0) === 1) {
    if (item.released_at && item.status === "Released") return "Funds issued";
    if (!item.released_at && activeStatuses.has(item.status)) return "Approved · not issued";
  }
  return item.status || "Unknown";
}

export default async function CashAdvancesPage({
  searchParams,
}: { searchParams?: Promise<{ review?: string; view?: string }> }) {
  const params = await searchParams;
  const reviewOnly = params?.review === "accounting";
  const selectedView: CashAdvanceView =
    params?.view === "awaiting" || params?.view === "outstanding" || params?.view === "closed"
      ? params.view : "all";
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  }

  const canEditExisting = ["owner", "payroll"].includes(session.role_key);
  const isOwner = session.role_key === "owner";
  const loaded = await Promise.allSettled([loadAdvances(), loadEmployees()]);
  const failed = loaded.find((result) => result.status === "rejected");
  if (failed?.status === "rejected") {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page"><section className="card"><strong>Cash advances unavailable</strong><p className="muted">{failed.reason instanceof Error ? failed.reason.message : "Try again shortly."}</p></section></div></Shell>;
  }

  const [advances, employees] = loaded.map((result) => result.status === "fulfilled" ? result.value : []) as [Advance[], Employee[]];
  // Approval is not disbursement. Prospective approved-but-unissued
  // advances must not inflate the issued outstanding or deduction metrics.
  const awaitingRelease = advances.filter((item) =>
    Number(item.release_confirmation_required || 0) === 1 &&
    !item.released_at &&
    activeStatuses.has(item.status) &&
    Number(item.remaining_balance || 0) > 0
  );
  const awaitingReleaseAmount = awaitingRelease.reduce((sum, item) => sum + Number(item.remaining_balance || 0), 0);
  const active = advances.filter((item) =>
    activeStatuses.has(item.status) &&
    Number(item.remaining_balance || 0) > 0 &&
    !(Number(item.release_confirmation_required || 0) === 1 && !item.released_at)
  );
  const totalBalance = active.reduce((sum, item) => sum + Number(item.remaining_balance || 0), 0);
  const totalRepaid = advances.reduce((sum, item) => sum + Number(item.total_repaid || 0), 0);
  const proposedDeduction = active.reduce((sum, item) => sum + Number(item.deduction_per_payroll || 0), 0);
  const creditToSettle = advances.reduce((sum, item) => sum + Number(item.overpayment_credit || 0), 0);
  const handoffExceptions = advances.flatMap((item) =>
    (item.repayments || []).filter(needsAccountingHandoffReview)
  );
  const exceptionAmountCentavos = handoffExceptions.reduce(
    (total, repayment) => total + Math.round(Number(repayment.amount || 0) * 100), 0
  );
  const affectedAdvanceIds = new Set(
    advances.filter((item) => (item.repayments || []).some(needsAccountingHandoffReview))
      .map((item) => item.id)
  );
  const closed = advances.filter((item) => item.status === "Fully Paid" || item.status === "Cancelled");
  const visibleAdvances = reviewOnly
    ? advances.filter((item) => affectedAdvanceIds.has(item.id))
    : selectedView === "awaiting" ? awaitingRelease
    : selectedView === "outstanding" ? active
    : selectedView === "closed" ? closed
    : advances;

  return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page cash-advance-page people-page">
    <PageHeading eyebrow="People" title="Cash advances" description="Track active employee balances, proposed payroll deductions, repayments, and overpayment credits." actions={<Link className="button secondary" href="/staff">Staff directory</Link>} />
    <section className="cash-summary-grid">
      <div className="cash-summary-card"><span>Active advances</span><strong>{active.length}</strong></div>
      <div className="cash-summary-card emphasis"><span>Outstanding</span><strong>{peso(totalBalance)}</strong></div>
      <div className="cash-summary-card"><span>Proposed next deductions</span><strong>{peso(proposedDeduction)}</strong></div>
      <div className="cash-summary-card"><span>Credits to settle</span><strong>{peso(creditToSettle)}</strong></div>
      <div className="cash-summary-card"><span>Approved, not issued</span><strong>{peso(awaitingReleaseAmount)}</strong><small>{awaitingRelease.length} advance{awaitingRelease.length === 1 ? "" : "s"} awaiting funds</small></div>
    </section>
    <section className="cash-accounting-review" aria-label="Staff Accounting handoff exceptions">
      <div className="cash-accounting-review-details">
        <span className="cash-accounting-review-kicker">Accounting handoff review</span>
        <div className="cash-accounting-review-total">
          <strong>{handoffExceptions.length} manual repayment{handoffExceptions.length === 1 ? "" : "s"}</strong>
          <span>{peso(exceptionAmountCentavos / 100)}</span>
        </div>
        <p>
          Missing, unsuccessful or unavailable Staff delivery records. This is not
          confirmation of an unposted Accounting receipt or missing funds.
          Reconcile original receipts before any event replay.
        </p>
      </div>
      <div className="cash-accounting-review-actions">
        {reviewOnly ? (
          <Link className="button secondary" href="/cash-advances">Show all advances</Link>
        ) : (
          <Link className="button secondary" href="/cash-advances?review=accounting">
            Review affected advances ({affectedAdvanceIds.size})
          </Link>
        )}
      </div>
    </section>
    <MobileSection title="Add cash advance" description="Open the form to record an employee advance"><section><CashAdvanceForm employees={employees} isOwner={isOwner} /></section></MobileSection>
    <nav className="cash-record-filters" aria-label="Cash advance record filters">
      {([
        { key: "all", href: "/cash-advances", label: "All records", count: advances.length },
        { key: "awaiting", href: "/cash-advances?view=awaiting", label: "Awaiting funds", count: awaitingRelease.length },
        { key: "outstanding", href: "/cash-advances?view=outstanding", label: "Outstanding", count: active.length },
        { key: "closed", href: "/cash-advances?view=closed", label: "Closed", count: closed.length },
      ] as const).map((filter) =>
        <Link key={filter.key} href={filter.href}
          className={`cash-record-filter${!reviewOnly && selectedView === filter.key ? " is-selected" : ""}`}
          aria-current={!reviewOnly && selectedView === filter.key ? "page" : undefined}>
          {filter.label} <span>{filter.count}</span>
        </Link>
      )}
    </nav>
    <section className="cash-card-list" aria-label={reviewOnly ? "Advances needing Accounting handoff review" : "Cash advance records"}>
      {visibleAdvances.map((item) => {
        const original = Number(item.amount || 0);
        const basis = Number(item.ledger_opening_balance ?? item.amount ?? 0);
        const balance = Number(item.remaining_balance || 0);
        const repaid = Number(item.total_repaid || 0);
        const credit = Number(item.overpayment_credit || 0);
        const paidPercent = basis > 0 ? Math.min(100, Math.max(0, (repaid / basis) * 100)) : 0;
        const isClosed = item.status === "Fully Paid" || item.status === "Cancelled";
        return <article className={`cash-advance-card${isClosed ? " is-closed" : ""}`} key={item.id}>
          <div className="cash-card-header">
            <div className="cash-card-person"><div className="cash-avatar" aria-hidden="true">{(item.full_name || "E").trim().charAt(0).toUpperCase()}</div><div><h2>{item.full_name || "Employee"}</h2><p>{item.employee_code || "No code"} · {item.department || "Unassigned"}</p></div></div>
            <StatusBadge label={statusLabel(item)} tone={item.status === "Fully Paid" ? "ok" : item.status === "Cancelled" ? "danger" : "warning"} />
          </div>
          <div className="cash-card-main">
            <div className="cash-balance-block"><span>{Number(item.release_confirmation_required || 0) === 1 && !item.released_at ? "Pending disbursement" : "Remaining balance"}</span><strong>{peso(balance)}</strong><small>{Number(item.release_confirmation_required || 0) === 1 && !item.released_at ? "Not yet included in issued outstanding" : `of ${peso(basis)} balance basis`}</small></div>
            <div className="cash-card-facts"><div><span>Repaid</span><strong>{peso(repaid)}</strong></div><div><span>Advance date</span><strong>{formatDate(item.advance_date)}</strong></div><div><span>Repayment</span><strong>{item.repayment_method || "Payroll deduction"}</strong></div></div>
          </div>
          <div className="cash-progress" aria-label={`${Math.round(paidPercent)}% repaid`}><div className="cash-progress-track"><span style={{ width: `${paidPercent}%` }} /></div><div className="cash-progress-label"><span>{Math.round(paidPercent)}% repaid</span><span>{balance <= 0 ? "Complete" : `${peso(balance)} left`}</span></div></div>
          {credit > 0 ? <div className="cash-reason"><span>Employee credit</span><p>{peso(credit)} was over-deducted and requires settlement.</p>{isOwner ? <CashAdvanceCreditSettlementForm advanceId={item.id} employeeId={item.employee_id} credit={credit} options={advances} /> : null}</div> : null}
          {item.reason ? <div className="cash-reason"><span>Reason</span><p>{item.reason}</p></div> : null}
          {item.released_at ? (
            <div className="cash-reason"><span>Funds issued</span>
              <p>{formatDate(item.released_at)} · {item.release_method || "Method not recorded"} · Accounting handoff is not proof of journal posting</p>
            </div>
          ) : Number(item.release_confirmation_required || 0) === 1 ? (
            <p className="cash-handoff-warning">Awaiting disbursement confirmation. Approval alone does not establish that cash was issued. Record actual release before collecting repayments.</p>
          ) : null}
          {(item.repayments || []).some(needsAccountingHandoffReview) ? (
            <p className="cash-handoff-warning">
              Manual repayment requires Staff Accounting handoff review. Verify the original receipt and Accounting ledger before any replay; a fully paid advance does not confirm cash posting.
            </p>
          ) : null}
          <div className="cash-card-footer">
            <div className="cash-primary-actions">
              {canEditExisting && Number(item.release_confirmation_required || 0) === 1 && !item.released_at && item.status === "Active" ? (
                <ConfirmCashAdvanceRelease advanceId={item.id} employeeName={item.full_name || "employee"} amount={original} advanceDate={item.advance_date} />
              ) : null}
              {canEditExisting && item.status !== "Cancelled" &&
              (Number(item.release_confirmation_required || 0) !== 1 || item.released_at) ? (
                <ManualRepaymentForm advanceId={item.id} balance={balance} employeeName={item.full_name || "employee"} />
              ) : null}
              {canEditExisting ? <CashAdvanceForm employees={employees} item={item} canEditExisting isOwner={isOwner} /> : null}
              {isOwner ? <CashAdvanceBalanceCorrection advanceId={item.id} employeeName={item.full_name || "employee"} currentBasis={basis} totalRepaid={repaid} /> : null}
            </div>
            <details className="cash-history"><summary>Repayment history <span>{item.repayments?.length || 0}</span></summary><div className="cash-history-list">{(item.repayments || []).map((repayment) => <div className="cash-history-row" key={repayment.id}><div><strong>{peso(repayment.amount)}</strong><span>{repayment.source}</span></div><div><strong>{formatDate(repayment.repayment_date)}</strong><span>{repayment.source === "Payroll" ? `${repayment.period_start || ""}–${repayment.period_end || ""}` : repayment.payment_method || "—"}</span></div><div><span>Recorded by</span><strong>{repayment.created_by || "—"}</strong>{accountingHandoffLabel(repayment) ? <span className="cash-handoff-status">{accountingHandoffLabel(repayment)}</span> : null}</div></div>)}{!item.repayments?.length ? <p className="cash-empty-history">No repayments recorded yet.</p> : null}</div></details>
          </div>
          {original !== basis ? <div className="cash-reason"><span>Original recorded amount</span><p>{peso(original)} · corrected balance basis {peso(basis)}</p></div> : null}
        </article>;
      })}
      {!visibleAdvances.length ? <section className="card cash-empty-state">
        <h2>{reviewOnly ? "No Staff handoff exceptions" : selectedView === "all" ? "No cash advances" : "No matching advances"}</h2>
        <p className="muted">{reviewOnly
          ? "No active manual repayments need a Staff Accounting delivery review. Delivered items still require separate Accounting posting verification."
          : selectedView === "all" ? "No employee advance records have been created." : "No advances match this filter. Select All records to see the full history."}</p>
      </section> : null}
    </section>
    <section className="people-card"><h2>Portfolio position</h2><p>{peso(totalRepaid)} has been repaid across all recorded advances.</p></section>
  </div></Shell>;
}
