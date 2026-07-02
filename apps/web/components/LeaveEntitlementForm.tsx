"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

type Employee = { id: number; full_name: string; employee_code?: string | null; department?: string | null };
type LeaveType = { id: number; name: string; default_credits?: number; paid?: number; active?: number };

type Props = {
  employees: Employee[];
  leaveTypes: LeaveType[];
  defaultYear: number;
};

export function LeaveEntitlementForm({ employees, leaveTypes, defaultYear }: Props) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const fallbackStart = `${defaultYear}-01-01`;
  const fallbackEnd = `${defaultYear}-12-31`;
  const firstType = leaveTypes[0];
  const defaultCredits = useMemo(() => Number(firstType?.default_credits || 0), [firstType]);

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");
    const payload = {
      employee_id: Number(formData.get("employee_id") || 0),
      leave_type_id: Number(formData.get("leave_type_id") || 0),
      year: Number(formData.get("year") || defaultYear),
      credits: Number(formData.get("credits") || 0),
      entitled: formData.get("entitled") === "on" ? 1 : 0,
      effective_start: String(formData.get("effective_start") || "") || null,
      effective_end: String(formData.get("effective_end") || "") || null,
    };
    const response = await fetch("/api/hr/leave-entitlements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(data.detail || data.message || "Entitlement was not saved.");
      return;
    }
    setMessage("Leave entitlement saved.");
    router.refresh();
  }

  return (
    <form action={submit} className="form-grid">
      <label>
        Employee
        <select name="employee_id" required>
          <option value="">Select employee</option>
          {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}
        </select>
      </label>
      <label>
        Leave type
        <select name="leave_type_id" required>
          <option value="">Select leave type</option>
          {leaveTypes.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
        </select>
      </label>
      <label>Credits<input name="credits" type="number" min="0" step="0.25" defaultValue={defaultCredits || 0} required /></label>
      <label>Year<input name="year" type="number" min="2020" max="2100" defaultValue={defaultYear} required /></label>
      <label>Effective start<input name="effective_start" type="date" defaultValue={fallbackStart} /></label>
      <label>Effective end<input name="effective_end" type="date" defaultValue={fallbackEnd} /></label>
      <label className="span-2"><input name="entitled" type="checkbox" defaultChecked /> Employee is entitled to this leave type</label>
      <div className="action-row form-span-full">
        <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : "Save entitlement"}</button>
        <p className="muted">Use the effective dates for hires, prorated eligibility, or backdated records. Leave dated inside this range counts against this entitlement.</p>
      </div>
      {message ? <p className="muted form-span-full" role="status">{message}</p> : null}
    </form>
  );
}
