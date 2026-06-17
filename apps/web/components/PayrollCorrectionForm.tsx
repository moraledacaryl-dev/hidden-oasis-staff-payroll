"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Employee } from "@/lib/types";

type Props = {
  runId: number;
  employees: Employee[];
};

export function PayrollCorrectionForm({ runId, employees }: Props) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");
    const payload = {
      run_id: runId,
      employee_id: Number(formData.get("employee_id")),
      adjustment_type: String(formData.get("adjustment_type") || "Earning"),
      amount: Number(formData.get("amount") || 0),
      reason: String(formData.get("reason") || "").trim(),
      apply_to_next_run: formData.get("apply_to_next_run") === "on",
    };

    const response = await fetch("/api/payroll/corrections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Correction was not saved.");
      return;
    }
    setMessage("Correction recorded.");
    router.refresh();
  }

  return (
    <form action={submit} className="form-grid">
      <label>
        Employee
        <select name="employee_id" required defaultValue="">
          <option value="" disabled>Select employee</option>
          {employees.map((employee) => (
            <option key={employee.id} value={employee.id}>{employee.full_name}</option>
          ))}
        </select>
      </label>
      <label>
        Type
        <select name="adjustment_type" defaultValue="Earning">
          <option>Earning</option>
          <option>Deduction</option>
          <option>Note</option>
        </select>
      </label>
      <label>
        Amount
        <input name="amount" type="number" step="0.01" defaultValue="0" />
      </label>
      <label>
        Reason
        <input name="reason" required minLength={3} placeholder="Required audit note" />
      </label>
      <label className="check-field">
        <input name="apply_to_next_run" type="checkbox" defaultChecked />
        Apply to next run when processed
      </label>
      <button className="primary-button" type="submit" disabled={busy}>{busy ? "Recording..." : "Record correction"}</button>
      {message ? <p className="muted">{message}</p> : null}
    </form>
  );
}
