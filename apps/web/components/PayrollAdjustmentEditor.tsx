"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppDrawer } from "@/components/AppSurface";
import styles from "./PayrollAdjustmentEditor.module.css";

type CashAdvance = {
  id: number;
  advance_date: string;
  amount: number;
  available_balance: number;
  deduction_per_payroll?: number | null;
  reason?: string | null;
};
type Adjustment = {
  additional_earning?: number;
  additional_earning_note?: string | null;
  other_deduction?: number;
  other_deduction_note?: string | null;
  cash_advance_id?: number | null;
  cash_advance_amount?: number;
  cash_advance_note?: string | null;
  version?: number;
};
type AdjustmentMode = "cash" | "earning" | "deduction";

function peso(value?: number | null): string {
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(Number(value || 0));
}

function roundMoney(value: number): number {
  return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}

function clampCashAmount(advance: CashAdvance, value: number): number {
  const available = Math.max(0, roundMoney(Number(advance.available_balance ?? 0)));
  const requested = Math.max(0, roundMoney(Number(value ?? 0)));
  return Math.min(available, requested);
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
  const [selectedAdvanceId, setSelectedAdvanceId] = useState<number | null>(null);
  const [cashAmount, setCashAmount] = useState(0);
  const [cashNote, setCashNote] = useState("");
  const [additionalEarning, setAdditionalEarning] = useState(0);
  const [additionalEarningNote, setAdditionalEarningNote] = useState("");
  const [otherDeduction, setOtherDeduction] = useState(0);
  const [otherDeductionNote, setOtherDeductionNote] = useState("");
  const [serverEditable, setServerEditable] = useState(true);

  const selectedAdvance = useMemo(() => advances.find((item) => item.id === selectedAdvanceId), [advances, selectedAdvanceId]);
  const suggestedCash = selectedAdvance ? clampCashAmount(selectedAdvance, Number(selectedAdvance.deduction_per_payroll ?? 0)) : 0;
  const cashNeedsReason = Boolean(selectedAdvanceId) && cashAmount > 0 && roundMoney(cashAmount) !== roundMoney(suggestedCash);
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
    setSelectedAdvanceId(current.cash_advance_id != null ? Number(current.cash_advance_id) : null);
    setCashAmount(Number(current.cash_advance_amount ?? 0));
    setCashNote(String(current.cash_advance_note || ""));
    setAdditionalEarning(Number(current.additional_earning ?? 0));
    setAdditionalEarningNote(String(current.additional_earning_note || ""));
    setOtherDeduction(Number(current.other_deduction ?? 0));
    setOtherDeductionNote(String(current.other_deduction_note || ""));
    setServerEditable(data.editable !== false);
  }, [employeeId, runId]);

  useEffect(() => { if (open) void load(); }, [load, open]);

  function chooseAdvance(value: string) {
    const id = value ? Number(value) : null;
    setSelectedAdvanceId(id);
    const item = advances.find((advance) => advance.id === id);
    if (!item) {
      setCashAmount(0);
      setCashNote("");
      return;
    }
    const saved = Number(adjustment.cash_advance_id) === id ? Number(adjustment.cash_advance_amount ?? 0) : null;
    const suggested = Number(item.deduction_per_payroll ?? 0);
    setCashAmount(clampCashAmount(item, saved ?? suggested));
    setCashNote(Number(adjustment.cash_advance_id) === id ? String(adjustment.cash_advance_note || "") : "");
  }

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
        cash_advance_id: selectedAdvanceId,
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
        description="Change one adjustment category at a time. The projected net pay updates before you save."
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
                <div className={styles.sectionTitle}><strong>Cash advance repayment</strong><span>Select the exact advance and amount to deduct in this payroll.</span></div>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Cash advance</span>
                  <select name="cash_advance_id" value={selectedAdvanceId || ""} onChange={(event) => chooseAdvance(event.target.value)}>
                    <option value="">No cash advance deduction</option>
                    {advances.map((advance) => <option key={advance.id} value={advance.id}>#{advance.id} · {advance.advance_date} · Available {peso(advance.available_balance)}</option>)}
                  </select>
                </label>
                <label className={styles.field}><span className={styles.fieldLabel}>Deduction this cutoff</span><input name="cash_advance_amount" type="number" min="0" max={selectedAdvance?.available_balance ?? 0} step="0.01" value={cashAmount} onChange={(event) => setCashAmount(Number(event.target.value || 0))} disabled={!selectedAdvanceId} /></label>
                {selectedAdvance ? <>
                  <div className={styles.balanceRow}><span>Suggested deduction</span><strong>{peso(suggestedCash)}</strong></div>
                  <div className={styles.balanceRow}><span>Available balance</span><strong>{peso(selectedAdvance.available_balance)}</strong></div>
                  <label className={styles.field}><span className={styles.fieldLabel}>Reason {cashNeedsReason ? "(required)" : "(optional)"}</span><input name="cash_advance_note" value={cashNote} onChange={(event) => setCashNote(event.target.value)} required={cashNeedsReason} placeholder={cashNeedsReason ? "Why this differs from the configured suggestion" : "Optional note"} /></label>
                </> : advances.length ? <p className={styles.helper}>Choose an advance to apply it to this payroll.</p> : <p className={styles.helper}>No available cash advances found for this employee.</p>}
              </section>
            ) : null}

            {mode === "earning" ? (
              <section className={styles.section} role="tabpanel">
                <div className={styles.sectionTitle}><strong>Additional earning</strong><span>Bonus, allowance, or one-time correction.</span></div>
                <label className={styles.field}><span className={styles.fieldLabel}>Amount</span><input name="additional_earning" type="number" min="0" step="0.01" value={additionalEarning} onChange={(event) => setAdditionalEarning(Number(event.target.value || 0))} /></label>
                <label className={styles.field}><span className={styles.fieldLabel}>Reason</span><input name="additional_earning_note" value={additionalEarningNote} onChange={(event) => setAdditionalEarningNote(event.target.value)} placeholder="Required whenever amount is nonzero" /></label>
              </section>
            ) : null}

            {mode === "deduction" ? (
              <section className={styles.section} role="tabpanel">
                <div className={styles.sectionTitle}><strong>Other deduction</strong><span>Uniform, damage, or another approved deduction.</span></div>
                <label className={styles.field}><span className={styles.fieldLabel}>Amount</span><input name="other_deduction" type="number" min="0" step="0.01" value={otherDeduction} onChange={(event) => setOtherDeduction(Number(event.target.value || 0))} /></label>
                <label className={styles.field}><span className={styles.fieldLabel}>Reason</span><input name="other_deduction_note" value={otherDeductionNote} onChange={(event) => setOtherDeductionNote(event.target.value)} placeholder="Required whenever amount is nonzero" /></label>
              </section>
            ) : null}

            {message ? <p className={styles.error}>{message}</p> : null}
          </div>
        )}
      </AppDrawer>
    </>
  );
}
