"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type AdvanceOption = {
  id: number;
  employee_id: number;
  full_name?: string | null;
  remaining_balance: number;
  status: string;
};

function peso(value: number): string {
  return Number(value || 0).toLocaleString("en-PH", {
    style: "currency",
    currency: "PHP",
  });
}

export function CashAdvanceCreditSettlementForm({
  advanceId,
  employeeId,
  credit,
  options = [],
}: {
  advanceId: number;
  employeeId: number;
  credit: number;
  options?: AdvanceOption[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState("Cash payout");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const targetOptions = options.filter((item) =>
    item.id !== advanceId &&
    item.employee_id === employeeId &&
    Number(item.remaining_balance || 0) > 0 &&
    !["Cancelled", "Fully Paid", "Pending", "Rejected"].includes(String(item.status || ""))
  );

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");

    const response = await fetch("/api/cash-advances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "settle_credit",
        cash_advance_id: advanceId,
        amount: Number(formData.get("amount") || 0),
        method: String(formData.get("method") || "Cash payout"),
        reference: String(formData.get("reference") || "") || null,
        note: String(formData.get("note") || ""),
        target_cash_advance_id: Number(formData.get("target_cash_advance_id") || 0) || null,
      }),
    });

    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(data.detail || "Credit settlement was not saved.");
      return;
    }

    setOpen(false);
    router.refresh();
  }

  if (!open) {
    return <button className="button small" type="button" onClick={() => setOpen(true)}>Settle credit</button>;
  }

  return (
    <form action={submit} className="cash-credit-settlement">
      <div>
        <strong>Settle employee credit</strong>
        <p className="muted">Available credit: {peso(credit)}</p>
      </div>

      <label>
        <span>Settlement amount</span>
        <input name="amount" type="number" min="0.01" max={credit} step="0.01" defaultValue={credit} required />
      </label>

      <label>
        <span>Method</span>
        <select name="method" value={method} onChange={(event) => setMethod(event.target.value)} required>
          <option>Cash payout</option>
          <option>Payroll reimbursement</option>
          <option>Offset another cash advance</option>
        </select>
      </label>

      {method === "Offset another cash advance" ? (
        <label>
          <span>Target cash advance</span>
          <select name="target_cash_advance_id" required>
            <option value="">Select target advance</option>
            {targetOptions.map((item) => (
              <option key={item.id} value={item.id}>
                #{item.id} · {peso(Number(item.remaining_balance || 0))} balance
              </option>
            ))}
          </select>
          {!targetOptions.length ? <small>No other active cash advance for this employee.</small> : null}
        </label>
      ) : null}

      <label>
        <span>Reference</span>
        <input name="reference" placeholder="Voucher, payroll run, receipt, or note reference" />
      </label>

      <label>
        <span>Settlement note</span>
        <textarea name="note" rows={3} placeholder="Example: Paid in cash by owner / reimbursed in payroll / offset against CA #..." required />
      </label>

      {message ? <p className="danger-text">{message}</p> : null}

      <div className="cash-edit-actions">
        <button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button>
        <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving…" : "Record settlement"}</button>
      </div>
    </form>
  );
}
