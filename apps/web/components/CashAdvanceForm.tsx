"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Employee = { id: number; full_name: string };
type Advance = {
  id?: number;
  employee_id?: number;
  advance_date?: string;
  amount?: number;
  reason?: string | null;
  approved_by?: string | null;
  repayment_method?: string | null;
  deduction_per_payroll?: number;
  remaining_balance?: number;
  status?: string | null;
  notes?: string | null;
};

export function CashAdvanceForm({ employees, item = null, canEditExisting = false }: { employees: Employee[]; item?: Advance | null; canEditExisting?: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(!item);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [method, setMethod] = useState(item?.repayment_method || "Payroll deduction");

  if (item && !canEditExisting) return null;

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");
    const body = {
      id: item?.id || null,
      employee_id: Number(formData.get("employee_id") || 0),
      advance_date: String(formData.get("advance_date") || ""),
      amount: Number(formData.get("amount") || 0),
      reason: String(formData.get("reason") || "") || null,
      approved_by: String(formData.get("approved_by") || "") || null,
      repayment_method: String(formData.get("repayment_method") || "Payroll deduction"),
      deduction_per_payroll: Number(formData.get("deduction_per_payroll") || 0),
      status: String(formData.get("status") || "Active"),
      notes: String(formData.get("notes") || "") || null,
    };
    const response = await fetch("/api/cash-advances", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Cash advance was not saved.");
      return;
    }
    setOpen(false);
    router.refresh();
  }

  if (!open) return <button className="button small" type="button" onClick={() => setOpen(true)}>Edit details</button>;

  return (
    <form action={submit} className="form-grid modal-form">
      <label>Employee<select name="employee_id" defaultValue={item?.employee_id || ""} required disabled={Boolean(item)}><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
      <label>Cash advance date<input name="advance_date" type="date" defaultValue={(item?.advance_date || "").slice(0, 10)} required /></label>
      <label>Advance amount<input name="amount" type="number" min="0.01" step="0.01" defaultValue={item?.amount ?? ""} required /></label>
      <label>Repayment setup<select name="repayment_method" value={method} onChange={(event) => setMethod(event.target.value)}><option>Payroll deduction</option><option>Manual repayment</option></select></label>
      {method === "Payroll deduction" ? <label>Suggested deduction per payroll<input name="deduction_per_payroll" type="number" min="0" step="0.01" defaultValue={item?.deduction_per_payroll ?? 0} /><span className="muted">Payroll may use the full balance or a smaller amount before finalizing each run.</span></label> : <input type="hidden" name="deduction_per_payroll" value="0" />}
      <label>Approved by<input name="approved_by" defaultValue={item?.approved_by || ""} placeholder="Name of approving supervisor or owner" /></label>
      <label>Reason<input name="reason" defaultValue={item?.reason || ""} placeholder="Purpose of the advance" /></label>
      <label>Notes<input name="notes" defaultValue={item?.notes || ""} placeholder="Optional internal note" /></label>
      {item ? <label>Status<select name="status" defaultValue={item?.status === "Approved" ? "Active" : item?.status || "Active"}><option>Active</option><option>Cancelled</option></select></label> : <input type="hidden" name="status" value="Active" />}
      <div className="badge-row"><button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving…" : item ? "Save changes" : "Add cash advance"}</button>{item ? <button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button> : null}</div>
      {message ? <p className="footer-note">{message}</p> : null}
    </form>
  );
}
