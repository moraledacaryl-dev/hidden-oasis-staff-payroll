"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Employee = { id: number; full_name: string };
type Advance = { id?: number; employee_id?: number; advance_date?: string; amount?: number; reason?: string | null; approved_by?: string | null; repayment_method?: string | null; deduction_per_payroll?: number; remaining_balance?: number; status?: string | null; notes?: string | null };

export function CashAdvanceForm({ employees, item = null }: { employees: Employee[]; item?: Advance | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(!item);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

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
      remaining_balance: Number(formData.get("remaining_balance") || 0),
      status: String(formData.get("status") || "Active"),
      notes: String(formData.get("notes") || "") || null,
    };
    const response = await fetch("/api/cash-advances", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Not saved.");
      return;
    }
    setOpen(false);
    router.refresh();
  }

  if (!open) return <button className="button small" type="button" onClick={() => setOpen(true)}>Edit</button>;

  return (
    <form action={submit} className="form-grid modal-form">
      <label>Employee<select name="employee_id" defaultValue={item?.employee_id || ""} required><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
      <label>Date<input name="advance_date" type="date" defaultValue={(item?.advance_date || "").slice(0, 10)} required /></label>
      <label>Amount<input name="amount" type="number" min="0" step="0.01" defaultValue={item?.amount ?? ""} required /></label>
      <label>Deduction per payroll<input name="deduction_per_payroll" type="number" min="0" step="0.01" defaultValue={item?.deduction_per_payroll ?? 0} /></label>
      <label>Remaining balance<input name="remaining_balance" type="number" min="0" step="0.01" defaultValue={item?.remaining_balance ?? item?.amount ?? 0} /></label>
      <label>Status<select name="status" defaultValue={item?.status || "Active"}><option>Active</option><option>Fully Paid</option><option>Cancelled</option></select></label>
      <label>Approved by<input name="approved_by" defaultValue={item?.approved_by || ""} /></label>
      <label>Repayment method<input name="repayment_method" defaultValue={item?.repayment_method || "Payroll deduction"} /></label>
      <label>Reason<input name="reason" defaultValue={item?.reason || ""} /></label>
      <label>Notes<input name="notes" defaultValue={item?.notes || ""} /></label>
      <div className="badge-row"><button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : "Save"}</button>{item ? <button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button> : null}</div>
      {message ? <p className="footer-note">{message}</p> : null}
    </form>
  );
}
