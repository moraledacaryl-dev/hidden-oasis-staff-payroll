"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Props = {
  employeeId: number;
  employeeName: string;
  periodMonth: string;
  suggestedAction: string;
};

const memoLevels = ["Verbal warning", "Formal memo", "Final written warning", "30-day improvement plan", "30-day probation", "Final review"];

export function AttendanceMemoForm({ employeeId, employeeName, periodMonth, suggestedAction }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");
    const body = {
      employee_id: employeeId,
      period_month: periodMonth,
      memo_type: String(formData.get("memo_type") || "Attendance"),
      memo_level: String(formData.get("memo_level") || "Verbal warning"),
      reason: String(formData.get("reason") || suggestedAction || "Attendance infraction"),
      notes: String(formData.get("notes") || "") || null,
      status: String(formData.get("status") || "Issued"),
    };
    const response = await fetch("/api/attendance/compliance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Memo was not saved.");
      return;
    }
    setOpen(false);
    router.refresh();
  }

  if (!open) {
    return <button className="button small" type="button" onClick={() => setOpen(true)}>Issue memo</button>;
  }

  return (
    <form action={submit} className="grid" style={{ minWidth: 280 }}>
      <strong>{employeeName}</strong>
      <label>Memo type<input name="memo_type" defaultValue="Attendance" /></label>
      <label>Memo level<select name="memo_level" defaultValue="Formal memo">{memoLevels.map((level) => <option key={level}>{level}</option>)}</select></label>
      <label>Reason<textarea name="reason" defaultValue={suggestedAction} rows={3} required /></label>
      <label>Notes<textarea name="notes" rows={2} /></label>
      <label>Status<select name="status" defaultValue="Issued"><option>Draft</option><option>Issued</option></select></label>
      <div className="badge-row">
        <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : "Save memo"}</button>
        <button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      {message ? <p className="footer-note">{message}</p> : null}
    </form>
  );
}
