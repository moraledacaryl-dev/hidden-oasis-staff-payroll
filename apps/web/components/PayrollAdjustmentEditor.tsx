"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type CashAdvance = { id: number; advance_date: string; amount: number; available_balance: number; reason?: string | null };
type Adjustment = { additional_earning?: number; additional_earning_note?: string | null; other_deduction?: number; other_deduction_note?: string | null; cash_advance_id?: number | null; cash_advance_amount?: number };

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
  }

  useEffect(() => { if (open) void load(); }, [open]);

  function chooseAdvance(value: string) {
    const id = value ? Number(value) : null;
    setSelectedAdvanceId(id);
    const item = advances.find((advance) => advance.id === id);
    setCashAmount(item ? Number(item.available_balance || 0) : 0);
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
  if (!open) return <button className="button small" type="button" onClick={() => setOpen(true)}>Add earnings / deductions</button>;

  return (
    <div className="card">
      <div className="panel-title"><div><h3>{employeeName}</h3><p className="muted">Add final earnings and deductions before sending payroll for review.</p></div></div>
      {loading ? <p className="muted">Loading adjustments…</p> : (
        <form action={submit} className="form-grid modal-form">
          <fieldset>
            <legend>Additional earning</legend>
            <label>Amount<input name="additional_earning" type="number" min="0" step="0.01" defaultValue={adjustment.additional_earning || 0} /></label>
            <label>Description<input name="additional_earning_note" defaultValue={adjustment.additional_earning_note || ""} placeholder="Bonus, allowance, correction…" /></label>
          </fieldset>
          <fieldset>
            <legend>Cash advance repayment</legend>
            <label>Cash advance<select value={selectedAdvanceId || ""} onChange={(event) => chooseAdvance(event.target.value)}><option value="">No cash advance deduction</option>{advances.map((advance) => <option key={advance.id} value={advance.id}>{advance.advance_date} · Balance ₱{advance.available_balance.toLocaleString("en-PH", { minimumFractionDigits: 2 })}</option>)}</select></label>
            <label>Deduction amount<input name="cash_advance_amount" type="number" min="0" max={selectedAdvance?.available_balance || 0} step="0.01" value={cashAmount} onChange={(event) => setCashAmount(Number(event.target.value || 0))} disabled={!selectedAdvanceId} /></label>
            {selectedAdvance ? <p className="muted">Prefilled with the full available balance. You may lower it, but it cannot exceed the balance.</p> : null}
          </fieldset>
          <fieldset>
            <legend>Other deduction</legend>
            <label>Amount<input name="other_deduction" type="number" min="0" step="0.01" defaultValue={adjustment.other_deduction || 0} /></label>
            <label>Description<input name="other_deduction_note" defaultValue={adjustment.other_deduction_note || ""} placeholder="Uniform, damage, correction…" /></label>
          </fieldset>
          <div className="badge-row"><button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving…" : "Save adjustments"}</button><button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button></div>
          {message ? <p className="footer-note">{message}</p> : null}
        </form>
      )}
    </div>
  );
}
