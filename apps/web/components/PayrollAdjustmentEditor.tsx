"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppDrawer } from "@/components/AppSurface";
import styles from "./PayrollAdjustmentEditor.module.css";

type CashAdvance = {
  id: number;
  advance_date?: string | null;
  request_date?: string | null;
  amount?: number;
  available_balance: number;
  deduction_per_payroll?: number | null;
  repayment_per_cutoff?: number | null;
  custom_next_deduction?: number | null;
  reason?: string | null;
};
type Adjustment = {
  additional_earning?: number;
  additional_earning_note?: string | null;
  other_deduction?: number;
  other_deduction_note?: string | null;
  cash_advance_amount?: number;
  cash_advance_note?: string | null;
  version?: number;
};
type Allocation = {
  cash_advance_id: number;
  advance_date?: string | null;
  amount: number;
  available_balance: number;
  reason?: string | null;
};
type AdjustmentMode = "cash" | "earning" | "deduction";

function peso(value?: number | null): string {
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(Number(value || 0));
}

function roundMoney(value: number): number {
  return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}

function allocateCash(advances: CashAdvance[], value: number): Allocation[] {
  let remaining = Math.max(0, roundMoney(value));
  const result: Allocation[] = [];
  for (const advance of advances) {
    if (remaining <= 0) break;
    const available = Math.max(0, roundMoney(Number(advance.available_balance ?? 0)));
    if (available <= 0) continue;
    const amount = Math.min(remaining, available);
    result.push({
      cash_advance_id: advance.id,
      advance_date: advance.advance_date || advance.request_date,
      amount: roundMoney(amount),
      available_balance: available,
      reason: advance.reason,
    });
    remaining = roundMoney(remaining - amount);
  }
  return result;
}

export function PayrollAdjustmentEditor({ runId, employeeId, employeeName, currentNetPay = 0, disabled = false }: { runId: number; employeeId: number; employeeName: string; currentNetPay?: number; disabled?: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<AdjustmentMode>("cash");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [advances, setAdvances] = useState<CashAdvance[]>([]);
  const [adjustment, setAdjustment] = useState<Adjustment>({});
  const [cashAmount, setCashAmount] = useState(0);
  const [cashNote, setCashNote] = useState("");
  const [cashTotalAvailable, setCashTotalAvailable] = useState(0);
  const [cashSuggested, setCashSuggested] = useState(0);
  const [reservedElsewhere, setReservedElsewhere] = useState(0);
  const [additionalEarning, setAdditionalEarning] = useState(0);
  const [additionalEarningNote, setAdditionalEarningNote] = useState("");
  const [otherDeduction, setOtherDeduction] = useState(0);
  const [otherDeductionNote, setOtherDeductionNote] = useState("");
  const [serverEditable, setServerEditable] = useState(true);

  const allocations = useMemo(() => allocateCash(advances, cashAmount), [advances, cashAmount]);
  const cashNeedsReason = cashAmount > 0 && Math.abs(roundMoney(cashAmount) - roundMoney(cashSuggested)) >= 0.005;
  const savedAdditional = Number(adjustment.additional_earning ?? 0);
  const savedOtherDeduction = Number(adjustment.other_deduction ?? 0);
  const savedCash = Number(adjustment.cash_advance_amount ?? 0);
  const projectedNetPay = roundMoney(Number(currentNetPay || 0) + (additionalEarning - savedAdditional) - (otherDeduction - savedOtherDeduction) - (cashAmount - savedCash));
  const projectedDelta = roundMoney(projectedNetPay - Number(currentNetPay || 0));

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    const response = await fetch(`/api/payroll/runs/${runId}/employees/${employeeId}/adjustments`, { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    setLoading(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Could not load adjustments.");
      return;
    }
    const current = data.adjustment || {};
    setAdvances(data.cash_advances || []);
    setAdjustment(current);
    setCashAmount(Number(current.cash_advance_amount ?? 0));
    setCashNote(String(current.cash_advance_note || ""));
    setCashTotalAvailable(Number(data.cash_advance_total_available ?? 0));
    setCashSuggested(Number(data.cash_advance_suggested ?? 0));
    setReservedElsewhere(Number(data.cash_advance_reserved_elsewhere ?? 0));
    setAdditionalEarning(Number(current.additional_earning ?? 0));
    setAdditionalEarningNote(String(current.additional_earning_note || ""));
    setOtherDeduction(Number(current.other_deduction ?? 0));
    setOtherDeductionNote(String(current.other_deduction_note || ""));
    setServerEditable(data.editable !== false);
  }, [employeeId, runId]);

  useEffect(() => { if (open) void load(); }, [load, open]);

  async function submit() {
    setBusy(true);
    setMessage("");
    const response = await fetch(`/api/payroll/runs/${runId}/employees/${employeeId}/adjustments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        additional_earning: additionalEarning,
        additional_earning_note: additionalEarningNote.trim() || null,
        other_deduction: otherDeduction,
        other_deduction_note: otherDeductionNote.trim() || null,
        cash_advance_id: null,
        cash_advance_amount: cashAmount,
        cash_advance_note: cashNote.trim() || null,
        expected_version: Number(adjustment.version ?? 0),
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Adjustments were not saved.");
      if (response.status === 409) void load();
      return;
    }
    setOpen(false);
    router.refresh();
  }

  if (disabled) return <span className="muted">Locked</span>;

  return (
    <>
      <button className="button small" type="button" onClick={() => { setMode("cash"); setOpen(true); }}>Adjust payroll</button>
      <AppDrawer
        open={open}
        eyebrow="Final adjustments"
        title={employeeName}
        description="Add a one-time earning or deduction, give it the label employees should see on the payslip, and preview the net-pay effect before saving."
        onClose={() => { if (!busy) setOpen(false); }}
        footer={serverEditable && !loading ? (
          <div className={styles.actions}>
            <button className="button ghost" type="button" onClick={() => setOpen(false)} disabled={busy}>Cancel</button>
            <button className="primary-button" type="button" onClick={submit} disabled={busy}>{busy ? "Saving…" : "Save adjustments"}</button>
          </div>
        ) : undefined}
      >
        {loading ? <p className={styles.helper}>Loading advances and adjustments…</p> : !serverEditable ? (
          <div className={styles.editor}><p className={styles.helper}>This paid-payroll revision is locked. Only the calculated employee difference can be settled.</p></div>
        ) : (
          <div className={styles.editor}>
            <div className={styles.modeTabs} role="tablist" aria-label="Adjustment type">
              <button type="button" role="tab" aria-selected={mode === "cash"} className={mode === "cash" ? styles.activeMode : ""} onClick={() => setMode("cash")}>Cash advance</button>
              <button type="button" role="tab" aria-selected={mode === "earning"} className={mode === "earning" ? styles.activeMode : ""} onClick={() => setMode("earning")}>Additional earning</button>
              <button type="button" role="tab" aria-selected={mode === "deduction"} className={mode === "deduction" ? styles.activeMode : ""} onClick={() => setMode("deduction")}>Other deduction</button>
            </div>

            <section className={styles.impact} aria-live="polite">
              <div><span>Current net pay</span><strong>{peso(currentNetPay)}</strong></div>
              <div><span>Projected net pay</span><strong>{peso(projectedNetPay)}</strong></div>
              <div><span>Change</span><strong>{projectedDelta >= 0 ? "+" : "−"}{peso(Math.abs(projectedDelta))}</strong></div>
            </section>

            {mode === "cash" ? (
              <section className={styles.section} role="tabpanel">
                <div className={styles.sectionTitle}>
                  <strong>Cash advance repayment</strong>
                  <span>Enter one deduction for this employee. It is automatically applied to eligible advances oldest first, so one payroll deduction can pay across several advances.</span>
                </div>
                <div className={styles.balanceRow}><span>Total available balance</span><strong>{peso(cashTotalAvailable)}</strong></div>
                <div className={styles.balanceRow}><span>Configured total this cutoff</span><strong>{peso(cashSuggested)}</strong></div>
                {reservedElsewhere > 0 ? <div className={styles.balanceRow}><span>Reserved by other draft payrolls</span><strong>{peso(reservedElsewhere)}</strong></div> : null}
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Deduction this cutoff</span>
                  <input name="cash_advance_amount" type="number" min="0" max={cashTotalAvailable} step="0.01" value={cashAmount} onChange={(event) => setCashAmount(Number(event.target.value || 0))} />
                </label>
                {cashTotalAvailable <= 0 && savedCash > 0 ? <p className={styles.helper}>No cash-advance balance is currently available to this draft. You can still reduce this saved deduction to ₱0 and save to clear it.</p> : null}
                {cashAmount > 0 ? (
                  <div className={styles.section}>
                    <div className={styles.sectionTitle}><strong>How this deduction will be applied</strong><span>Oldest eligible advance first.</span></div>
                    {allocations.map((allocation) => (
                      <div className={styles.balanceRow} key={allocation.cash_advance_id}>
                        <span>#{allocation.cash_advance_id} · {allocation.advance_date || "Undated"}{allocation.reason ? ` · ${allocation.reason}` : ""}</span>
                        <strong>{peso(allocation.amount)}</strong>
                      </div>
                    ))}
                  </div>
                ) : advances.length ? <p className={styles.helper}>No deduction is selected for this cutoff.</p> : <p className={styles.helper}>No eligible payroll-deduction cash advances are available for this employee.</p>}
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Reason {cashNeedsReason ? "(required)" : "(optional)"}</span>
                  <input name="cash_advance_note" value={cashNote} onChange={(event) => setCashNote(event.target.value)} required={cashNeedsReason} placeholder={cashNeedsReason ? "Why this differs from the configured total" : "Optional note"} />
                </label>
              </section>
            ) : null}

            {mode === "earning" ? (
              <section className={styles.section} role="tabpanel">
                <div className={styles.sectionTitle}><strong>Additional earning</strong><span>Bonus, allowance, incentive, or another one-time earning.</span></div>
                <label className={styles.field}><span className={styles.fieldLabel}>Amount</span><input name="additional_earning" type="number" min="0" step="0.01" value={additionalEarning} onChange={(event) => setAdditionalEarning(Number(event.target.value || 0))} /></label>
                <label className={styles.field}><span className={styles.fieldLabel}>Payslip label</span><input name="additional_earning_note" value={additionalEarningNote} onChange={(event) => setAdditionalEarningNote(event.target.value)} placeholder="e.g. Performance incentive" required={additionalEarning > 0} /></label>
                <p className={styles.helper}>This exact label will appear beside the amount on the employee and company payslip copies.</p>
              </section>
            ) : null}

            {mode === "deduction" ? (
              <section className={styles.section} role="tabpanel">
                <div className={styles.sectionTitle}><strong>Other deduction</strong><span>Uniform, damage, shortage, or another approved one-time deduction.</span></div>
                <label className={styles.field}><span className={styles.fieldLabel}>Amount</span><input name="other_deduction" type="number" min="0" step="0.01" value={otherDeduction} onChange={(event) => setOtherDeduction(Number(event.target.value || 0))} /></label>
                <label className={styles.field}><span className={styles.fieldLabel}>Payslip label</span><input name="other_deduction_note" value={otherDeductionNote} onChange={(event) => setOtherDeductionNote(event.target.value)} placeholder="e.g. Uniform deduction" required={otherDeduction > 0} /></label>
                <p className={styles.helper}>This exact label will appear beside the amount on the employee and company payslip copies.</p>
              </section>
            ) : null}

            {message ? <p className={styles.error}>{message}</p> : null}
          </div>
        )}
      </AppDrawer>
    </>
  );
}
