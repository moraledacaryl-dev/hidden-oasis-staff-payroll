"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Employee = { id: number; full_name: string };
type Advance = {
  id?: number; employee_id?: number; advance_date?: string; amount?: number;
  ledger_opening_balance?: number | null; reason?: string | null; approved_by?: string | null;
  repayment_method?: string | null; deduction_per_payroll?: number; total_repaid?: number;
  status?: string | null; notes?: string | null;
};

export function CashAdvanceFormV2({ employees, item = null, canEditExisting = false, isOwner = false }: { employees: Employee[]; item?: Advance | null; canEditExisting?: boolean; isOwner?: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(!item);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [method, setMethod] = useState(item?.repayment_method || "Payroll deduction");
  const encodedAmount = Number(item?.amount || 0);
  const currentBasis = Number(item?.ledger_opening_balance ?? item?.amount ?? 0);
  const [amount, setAmount] = useState(item ? currentBasis : 0);

  if (item && !canEditExisting) return null;

  const totalRepaid = Number(item?.total_repaid || 0);
  const changed = Boolean(item) && Math.abs(amount - currentBasis) >= 0.005;
  const newBalance = Math.max(0, amount - totalRepaid);
  const credit = Math.max(0, totalRepaid - amount);

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");

    if (item && changed) {
      const reason = String(formData.get("correction_reason") || "").trim();
      if (!isOwner || !reason) {
        setBusy(false);
        setMessage(!isOwner ? "Only the owner can correct the balance basis." : "Enter a correction reason.");
        return;
      }
      const correction = await fetch("/api/cash-advances", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "correct_amount", cash_advance_id: item.id, corrected_amount: amount, correction_reason: reason, reference: String(formData.get("correction_reference") || "") || null }),
      });
      const result = await correction.json().catch(() => ({}));
      if (!correction.ok || !result.ok) {
        setBusy(false);
        setMessage(result.detail || "Balance correction was not saved.");
        return;
      }
    }

    const saveAmount = item ? (changed ? amount : encodedAmount) : amount;
    const response = await fetch("/api/cash-advances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: item?.id || null,
        employee_id: Number(formData.get("employee_id") || 0),
        advance_date: String(formData.get("advance_date") || ""),
        amount: saveAmount,
        reason: String(formData.get("reason") || "") || null,
        approved_by: String(formData.get("approved_by") || "") || null,
        repayment_method: String(formData.get("repayment_method") || "Payroll deduction"),
        deduction_per_payroll: Number(formData.get("deduction_per_payroll") || 0),
        status: String(formData.get("status") || "Active"),
        notes: String(formData.get("notes") || "") || null,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(data.detail || "Cash advance was not saved.");
      return;
    }
    setOpen(false);
    router.refresh();
  }

  if (!open) return <button className="button small" type="button" onClick={() => setOpen(true)}>Edit details</button>;

  return (
    <form action={submit} className="form-grid modal-form">
      {item ? <input type="hidden" name="employee_id" value={item.employee_id || ""} /> : null}
      <label>Employee<select name={item ? undefined : "employee_id"} defaultValue={item?.employee_id || ""} required disabled={Boolean(item)}><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
      <label>Cash advance date<input name="advance_date" type="date" defaultValue={(item?.advance_date || "").slice(0, 10)} required /></label>
      <label>{item ? "Balance basis" : "Original advance amount"}<input type="number" min="0.01" step="0.01" value={amount || ""} onChange={(event) => setAmount(Number(event.target.value || 0))} disabled={Boolean(item) && !isOwner} required />{item ? <small className="muted">Current basis: ₱{currentBasis.toLocaleString("en-PH", { minimumFractionDigits: 2 })}. Confirmed repayments stay applied.</small> : null}</label>
      <label>Repayment setup<select name="repayment_method" value={method} onChange={(event) => setMethod(event.target.value)}><option>Payroll deduction</option><option>Manual repayment</option></select></label>
      {method === "Payroll deduction" ? <label>Suggested deduction per payroll<input name="deduction_per_payroll" type="number" min="0" step="0.01" defaultValue={item?.deduction_per_payroll ?? 0} /></label> : <input type="hidden" name="deduction_per_payroll" value="0" />}
      <label>Approved by<input name="approved_by" defaultValue={item?.approved_by || ""} /></label>
      <label>Reason<input name="reason" defaultValue={item?.reason || ""} /></label>
      <label>Notes<input name="notes" defaultValue={item?.notes || ""} /></label>
      {item ? <label>Status<select name="status" defaultValue={item.status === "Approved" ? "Active" : item.status || "Active"}><option>Active</option><option>Cancelled</option></select></label> : <input type="hidden" name="status" value="Active" />}
      {item && changed ? <fieldset><legend>Owner correction</legend><p>Previous basis: ₱{currentBasis.toLocaleString("en-PH", { minimumFractionDigits: 2 })}</p><p>Repayments applied: ₱{totalRepaid.toLocaleString("en-PH", { minimumFractionDigits: 2 })}</p><p>New balance: ₱{newBalance.toLocaleString("en-PH", { minimumFractionDigits: 2 })}</p>{credit > 0 ? <p>Employee credit: ₱{credit.toLocaleString("en-PH", { minimumFractionDigits: 2 })}</p> : null}<label>Correction reason<input name="correction_reason" required /></label><label>Reference<input name="correction_reference" /></label></fieldset> : null}
      <div className="badge-row"><button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving…" : item ? "Save changes" : "Add cash advance"}</button>{item ? <button className="button ghost" type="button" onClick={() => { setAmount(currentBasis); setOpen(false); }}>Cancel</button> : null}</div>
      {message ? <p className="footer-note">{message}</p> : null}
    </form>
  );
}
