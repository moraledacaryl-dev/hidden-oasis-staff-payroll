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
    <>
      <form action={submit} className={`cash-edit-panel${item ? " is-editing" : ""}`}>
        {item ? <input type="hidden" name="employee_id" value={item.employee_id || ""} /> : null}

        <div className="cash-edit-header">
          <div>
            <span className="cash-edit-eyebrow">{item ? "Edit cash advance" : "New cash advance"}</span>
            <h3>{item ? "Update advance details" : "Add advance"}</h3>
            <p>{item ? "Change repayment settings or correct the balance basis." : "Record the advance and repayment setup."}</p>
          </div>
          {item ? <button className="cash-edit-close" type="button" aria-label="Close" onClick={() => { setAmount(currentBasis); setOpen(false); }}>×</button> : null}
        </div>

        <div className="cash-edit-grid">
          <label className="cash-edit-field">
            <span>Employee</span>
            <select name={item ? undefined : "employee_id"} defaultValue={item?.employee_id || ""} required disabled={Boolean(item)}>
              <option value="">Select employee</option>
              {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}
            </select>
          </label>

          <label className="cash-edit-field">
            <span>Advance date</span>
            <input name="advance_date" type="date" defaultValue={(item?.advance_date || "").slice(0, 10)} required />
          </label>

          <label className="cash-edit-field cash-edit-field-emphasis">
            <span>{item ? "Balance basis" : "Original amount"}</span>
            <input type="number" min="0.01" step="0.01" value={amount || ""} onChange={(event) => setAmount(Number(event.target.value || 0))} disabled={Boolean(item) && !isOwner} required />
            {item ? <small>Confirmed repayments remain applied.</small> : null}
          </label>

          <label className="cash-edit-field">
            <span>Repayment method</span>
            <select name="repayment_method" value={method} onChange={(event) => setMethod(event.target.value)}>
              <option>Payroll deduction</option>
              <option>Manual repayment</option>
            </select>
          </label>

          {method === "Payroll deduction" ? (
            <label className="cash-edit-field">
              <span>Suggested deduction</span>
              <input name="deduction_per_payroll" type="number" min="0" step="0.01" defaultValue={item?.deduction_per_payroll ?? 0} />
              <small>Can still be changed during payroll review.</small>
            </label>
          ) : <input type="hidden" name="deduction_per_payroll" value="0" />}

          <label className="cash-edit-field">
            <span>Approved by</span>
            <input name="approved_by" defaultValue={item?.approved_by || ""} placeholder="Supervisor or owner" />
          </label>

          <label className="cash-edit-field cash-edit-span-2">
            <span>Reason</span>
            <input name="reason" defaultValue={item?.reason || ""} placeholder="Purpose of the advance" />
          </label>

          <label className="cash-edit-field cash-edit-span-2">
            <span>Notes</span>
            <textarea name="notes" defaultValue={item?.notes || ""} rows={3} placeholder="Optional internal note" />
          </label>

          {item ? (
            <label className="cash-edit-field">
              <span>Status</span>
              <select name="status" defaultValue={item.status === "Approved" ? "Active" : item.status || "Active"}>
                <option>Active</option>
                <option>Cancelled</option>
              </select>
            </label>
          ) : <input type="hidden" name="status" value="Active" />}
        </div>

        {item && changed ? (
          <section className="cash-correction-card">
            <div className="cash-correction-heading">
              <div><span>Owner correction</span><h4>Review balance change</h4></div>
              <strong>{newBalance.toLocaleString("en-PH", { style: "currency", currency: "PHP" })} remaining</strong>
            </div>
            <div className="cash-correction-stats">
              <div><span>Previous basis</span><strong>{currentBasis.toLocaleString("en-PH", { style: "currency", currency: "PHP" })}</strong></div>
              <div><span>Corrected basis</span><strong>{amount.toLocaleString("en-PH", { style: "currency", currency: "PHP" })}</strong></div>
              <div><span>Repayments applied</span><strong>{totalRepaid.toLocaleString("en-PH", { style: "currency", currency: "PHP" })}</strong></div>
            </div>
            {credit > 0 ? <p className="cash-credit-alert">This creates an employee credit of {credit.toLocaleString("en-PH", { style: "currency", currency: "PHP" })}.</p> : null}
            <div className="cash-correction-fields">
              <label className="cash-edit-field"><span>Correction reason</span><input name="correction_reason" required placeholder="Why the balance basis was incorrect" /></label>
              <label className="cash-edit-field"><span>Reference</span><input name="correction_reference" placeholder="Optional voucher or accounting reference" /></label>
            </div>
          </section>
        ) : null}

        <div className="cash-edit-actions">
          {message ? <p>{message}</p> : <span />}
          <div>
            {item ? <button className="button ghost" type="button" onClick={() => { setAmount(currentBasis); setOpen(false); }}>Cancel</button> : null}
            <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving…" : item ? "Save changes" : "Add cash advance"}</button>
          </div>
        </div>
      </form>

      <style jsx>{`
        .cash-edit-panel{display:grid;gap:18px;width:100%;padding:18px;border:1px solid var(--line);border-radius:18px;background:var(--surface);box-shadow:0 14px 35px rgba(26,35,50,.08)}
        .cash-edit-header{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;padding-bottom:14px;border-bottom:1px solid var(--line)}
        .cash-edit-header h3{margin:2px 0 4px;font-size:1.05rem}.cash-edit-header p{margin:0;color:var(--muted);font-size:.82rem}.cash-edit-eyebrow{color:var(--accent);font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em}
        .cash-edit-close{width:32px;height:32px;border:1px solid var(--line);border-radius:10px;background:var(--surface-soft);color:var(--muted);font-size:1.2rem;line-height:1;cursor:pointer}
        .cash-edit-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 16px}.cash-edit-field{display:grid;gap:6px;min-width:0}.cash-edit-field>span{color:var(--muted);font-size:.7rem;font-weight:850;text-transform:uppercase;letter-spacing:.065em}.cash-edit-field input,.cash-edit-field select,.cash-edit-field textarea{width:100%;min-width:0}.cash-edit-field textarea{resize:vertical}.cash-edit-field small{color:var(--muted);font-size:.74rem;line-height:1.35}.cash-edit-span-2{grid-column:1/-1}
        .cash-edit-field-emphasis{padding:12px;border:1px solid var(--accent-soft);border-radius:13px;background:var(--accent-soft)}.cash-edit-field-emphasis input{background:var(--surface)}
        .cash-correction-card{display:grid;gap:14px;padding:16px;border:1px solid #e9c982;border-radius:15px;background:var(--warning-soft)}.cash-correction-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.cash-correction-heading span{color:var(--warning);font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em}.cash-correction-heading h4{margin:2px 0 0}.cash-correction-heading>strong{color:var(--warning);white-space:nowrap}.cash-correction-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.cash-correction-stats div{display:grid;gap:4px;padding:11px;border-radius:11px;background:rgba(255,255,255,.72)}.cash-correction-stats span{color:var(--muted);font-size:.67rem;font-weight:800;text-transform:uppercase;letter-spacing:.055em}.cash-correction-fields{display:grid;grid-template-columns:1fr 1fr;gap:12px}.cash-credit-alert{margin:0;padding:10px 12px;border-radius:10px;background:rgba(255,255,255,.72);color:var(--danger);font-size:.8rem;font-weight:750}
        .cash-edit-actions{display:flex;justify-content:space-between;align-items:center;gap:12px;padding-top:14px;border-top:1px solid var(--line)}.cash-edit-actions>p{margin:0;color:var(--danger);font-size:.8rem;font-weight:700}.cash-edit-actions>div{display:flex;gap:8px;margin-left:auto}
        @media(max-width:720px){.cash-edit-panel{padding:14px}.cash-edit-grid,.cash-correction-stats,.cash-correction-fields{grid-template-columns:1fr}.cash-edit-span-2{grid-column:1}.cash-correction-heading,.cash-edit-actions{display:grid}.cash-correction-heading>strong{white-space:normal}.cash-edit-actions>div{width:100%;margin-left:0}.cash-edit-actions button{flex:1}}
      `}</style>
    </>
  );
}
