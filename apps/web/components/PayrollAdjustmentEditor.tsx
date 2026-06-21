"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./PayrollAdjustmentEditor.module.css";

type CashAdvance = { id: number; advance_date: string; amount: number; available_balance: number; reason?: string | null };
type Adjustment = { additional_earning?: number; additional_earning_note?: string | null; other_deduction?: number; other_deduction_note?: string | null; cash_advance_id?: number | null; cash_advance_amount?: number };

function peso(value?: number | null): string {
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(Number(value || 0));
}

export function PayrollAdjustmentEditor({ runId, employeeId, employeeName, disabled = false }: { runId: number; employeeId: number; employeeName: string; disabled?: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [advances, setAdvances] = useState<CashAdvance[]>([]);
  const [adjustment, setAdjustment] = useState<Adjustment>({});
  const [selectedAdvanceId, setSelectedAdvanceId] = useState<number | null>(null);
  const [cashAmount, setCashAmount] = useState(0);
  const [serverEditable, setServerEditable] = useState(true);

  const selectedAdvance = useMemo(() => advances.find((item) => item.id === selectedAdvanceId), [advances, selectedAdvanceId]);

  async function load() {
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
    setSelectedAdvanceId(current.cash_advance_id ? Number(current.cash_advance_id) : null);
    setCashAmount(Number(current.cash_advance_amount || 0));
    setServerEditable(data.editable !== false);
  }

  useEffect(() => { if (open) void load(); }, [open]);

  function chooseAdvance(value: string) {
    const id = value ? Number(value) : null;
    setSelectedAdvanceId(id);
    const item = advances.find((advance) => advance.id === id);
    setCashAmount(item ? Math.min(Number(item.available_balance || 0), Number(adjustment.cash_advance_amount || item.available_balance || 0)) : 0);
  }

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");
    const response = await fetch(`/api/payroll/runs/${runId}/employees/${employeeId}/adjustments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        additional_earning: Number(formData.get("additional_earning") || 0),
        additional_earning_note: String(formData.get("additional_earning_note") || "") || null,
        other_deduction: Number(formData.get("other_deduction") || 0),
        other_deduction_note: String(formData.get("other_deduction_note") || "") || null,
        cash_advance_id: selectedAdvanceId,
        cash_advance_amount: Number(formData.get("cash_advance_amount") || 0),
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Adjustments were not saved.");
      return;
    }
    setOpen(false);
    router.refresh();
  }

  if (disabled) return <span className="muted">Locked</span>;
  if (!open) return <button className="button small" type="button" onClick={() => setOpen(true)}>Edit earnings / deductions</button>;

  if (!loading && !serverEditable) {
    return (
      <div className={styles.editor}>
        <div className={styles.headerCopy}>
          <h3>{employeeName}</h3>
          <p className={styles.helper}>This paid-payroll revision is locked. Only the calculated employee difference can be settled.</p>
        </div>
        <div className={styles.actions}><button className="button ghost" type="button" onClick={() => setOpen(false)}>Close</button></div>
      </div>
    );
  }

  return (
    <div className={styles.editor}>
      <div className={styles.header}>
        <div className={styles.headerCopy}>
          <h3>{employeeName}</h3>
          <p className={styles.helper}>Enter the final amounts for this employee. Saving replaces the current values; it does not add another adjustment.</p>
        </div>
      </div>

      {loading ? <p className={styles.helper}>Loading adjustments…</p> : (
        <form action={submit}>
          <div className={styles.grid}>
            <section className={styles.section}>
              <div className={styles.sectionTitle}><strong>Additional earning</strong><span>Bonus, allowance, or one-time correction.</span></div>
              <label className={styles.field}><span className={styles.fieldLabel}>Amount</span><input name="additional_earning" type="number" min="0" step="0.01" defaultValue={adjustment.additional_earning || 0} /></label>
              <label className={styles.field}><span className={styles.fieldLabel}>Description</span><input name="additional_earning_note" defaultValue={adjustment.additional_earning_note || ""} placeholder="Optional note" /></label>
            </section>

            <section className={styles.section}>
              <div className={styles.sectionTitle}><strong>Cash advance repayment</strong><span>Select the advance and enter the final deduction for this payroll.</span></div>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Cash advance</span>
                <select value={selectedAdvanceId || ""} onChange={(event) => chooseAdvance(event.target.value)}>
                  <option value="">No cash advance deduction</option>
                  {advances.map((advance) => <option key={advance.id} value={advance.id}>{advance.advance_date} · Available {peso(advance.available_balance)}</option>)}
                </select>
              </label>
              <label className={styles.field}><span className={styles.fieldLabel}>Deduction amount</span><input name="cash_advance_amount" type="number" min="0" max={selectedAdvance?.available_balance || 0} step="0.01" value={cashAmount} onChange={(event) => setCashAmount(Number(event.target.value || 0))} disabled={!selectedAdvanceId} /></label>
              {selectedAdvance ? <div className={styles.balanceRow}><span>Available balance</span><strong>{peso(selectedAdvance.available_balance)}</strong></div> : null}
            </section>

            <section className={styles.section}>
              <div className={styles.sectionTitle}><strong>Other deduction</strong><span>Uniform, damage, or another approved deduction.</span></div>
              <label className={styles.field}><span className={styles.fieldLabel}>Amount</span><input name="other_deduction" type="number" min="0" step="0.01" defaultValue={adjustment.other_deduction || 0} /></label>
              <label className={styles.field}><span className={styles.fieldLabel}>Description</span><input name="other_deduction_note" defaultValue={adjustment.other_deduction_note || ""} placeholder="Optional note" /></label>
            </section>
          </div>

          {message ? <p className={styles.error}>{message}</p> : null}
          <div className={styles.actions}>
            <button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button>
            <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving…" : "Save final values"}</button>
          </div>
        </form>
      )}
    </div>
  );
}
