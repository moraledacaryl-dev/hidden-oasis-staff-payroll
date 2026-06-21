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
    <>
      <form action={submit} className={`cash-advance-form${item ? " cash-advance-form-edit" : ""}`}>
        {item ? <input type="hidden" name="employee_id" value={item.employee_id || ""} /> : null}

        <label className="cash-field">
          <span>Employee</span>
          <select name={item ? undefined : "employee_id"} defaultValue={item?.employee_id || ""} required disabled={Boolean(item)}>
            <option value="">Select employee</option>
            {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}
          </select>
        </label>

        <label className="cash-field">
          <span>Cash advance date</span>
          <input name="advance_date" type="date" defaultValue={(item?.advance_date || "").slice(0, 10)} required />
        </label>

        <label className="cash-field">
          <span>Advance amount</span>
          <input name="amount" type="number" min="0.01" step="0.01" defaultValue={item?.amount ?? ""} required />
        </label>

        <label className="cash-field">
          <span>Repayment setup</span>
          <select name="repayment_method" value={method} onChange={(event) => setMethod(event.target.value)}>
            <option>Payroll deduction</option>
            <option>Manual repayment</option>
          </select>
        </label>

        {method === "Payroll deduction" ? (
          <label className="cash-field cash-field-deduction">
            <span>Suggested deduction per payroll</span>
            <input name="deduction_per_payroll" type="number" min="0" step="0.01" defaultValue={item?.deduction_per_payroll ?? 0} />
            <small>Suggested amount only. Payroll may change it before finalizing the run.</small>
          </label>
        ) : <input type="hidden" name="deduction_per_payroll" value="0" />}

        <label className="cash-field">
          <span>Approved by</span>
          <input name="approved_by" defaultValue={item?.approved_by || ""} placeholder="Supervisor or owner" />
        </label>

        <label className="cash-field">
          <span>Reason</span>
          <input name="reason" defaultValue={item?.reason || ""} placeholder="Purpose of the advance" />
        </label>

        <label className="cash-field">
          <span>Notes</span>
          <input name="notes" defaultValue={item?.notes || ""} placeholder="Optional internal note" />
        </label>

        {item ? (
          <label className="cash-field">
            <span>Status</span>
            <select name="status" defaultValue={item?.status === "Approved" ? "Active" : item?.status || "Active"}>
              <option>Active</option>
              <option>Cancelled</option>
            </select>
          </label>
        ) : <input type="hidden" name="status" value="Active" />}

        <div className="cash-form-actions">
          {message ? <p className="cash-form-message">{message}</p> : <span />}
          <div className="action-row">
            {item ? <button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button> : null}
            <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving…" : item ? "Save changes" : "Add cash advance"}</button>
          </div>
        </div>
      </form>

      <style jsx>{`
        .cash-advance-form {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 14px 16px;
          align-items: start;
          min-width: 0;
        }
        .cash-field {
          display: grid;
          gap: 6px;
          min-width: 0;
        }
        .cash-field > span {
          color: var(--muted);
          font-size: 0.72rem;
          font-weight: 820;
          text-transform: uppercase;
          letter-spacing: 0.07em;
        }
        .cash-field input,
        .cash-field select {
          width: 100%;
          min-width: 0;
        }
        .cash-field small {
          color: var(--muted);
          font-size: 0.76rem;
          font-weight: 500;
          line-height: 1.35;
          text-transform: none;
          letter-spacing: normal;
        }
        .cash-field-deduction {
          grid-column: span 2;
        }
        .cash-form-actions {
          grid-column: 1 / -1;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          padding-top: 2px;
        }
        .cash-form-actions .action-row {
          margin-left: auto;
        }
        .cash-form-message {
          color: var(--danger);
          font-size: 0.82rem;
          font-weight: 700;
        }
        .cash-advance-form-edit {
          grid-template-columns: repeat(2, minmax(0, 1fr));
          width: 100%;
          margin-top: 10px;
          padding: 14px;
          border: 1px solid var(--line);
          border-radius: 14px;
          background: var(--surface-soft);
        }
        .cash-advance-form-edit .cash-field-deduction {
          grid-column: span 2;
        }
        @media (max-width: 1080px) {
          .cash-advance-form {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
          .cash-field-deduction,
          .cash-form-actions {
            grid-column: 1 / -1;
          }
        }
        @media (max-width: 720px) {
          .cash-advance-form,
          .cash-advance-form-edit {
            grid-template-columns: 1fr;
          }
          .cash-field-deduction,
          .cash-advance-form-edit .cash-field-deduction,
          .cash-form-actions {
            grid-column: 1;
          }
          .cash-form-actions {
            display: grid;
          }
          .cash-form-actions > span {
            display: none;
          }
          .cash-form-actions .action-row {
            width: 100%;
            margin-left: 0;
          }
        }
      `}</style>
    </>
  );
}
