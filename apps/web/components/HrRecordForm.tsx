"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const recordTypes = ["Memo", "Infraction", "Annual Review"];
const severities = ["Info", "Low", "Medium", "High", "Final"];
const statuses = ["Draft", "Issued", "Acknowledged", "Resolved", "Voided"];

type Employee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };

export function HrRecordForm({ employees }: { employees: Employee[] }) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");
    const payload = {
      employee_id: Number(formData.get("employee_id") || 0),
      record_type: String(formData.get("record_type") || "Memo"),
      record_date: String(formData.get("record_date") || new Date().toISOString().slice(0, 10)),
      subject: String(formData.get("subject") || "").trim(),
      details: String(formData.get("details") || "").trim() || null,
      severity: String(formData.get("severity") || "Info"),
      status: String(formData.get("status") || "Issued"),
      review_period_start: String(formData.get("review_period_start") || "") || null,
      review_period_end: String(formData.get("review_period_end") || "") || null,
      rating: String(formData.get("rating") || "") ? Number(formData.get("rating")) : null,
    };
    const res = await fetch("/api/hr/records", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await res.json().catch(() => ({}));
    setBusy(false);
    if (!res.ok || !data.ok) {
      setMessage(data.detail || data.message || "Record was not saved.");
      return;
    }
    setMessage("HR record saved.");
    router.refresh();
  }

  return (
    <form action={submit} className="form-grid">
      <label>Employee<select name="employee_id" required><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
      <label>Type<select name="record_type" defaultValue="Memo">{recordTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
      <label>Date<input name="record_date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required /></label>
      <label>Severity<select name="severity" defaultValue="Info">{severities.map((severity) => <option key={severity}>{severity}</option>)}</select></label>
      <label>Status<select name="status" defaultValue="Issued">{statuses.map((status) => <option key={status}>{status}</option>)}</select></label>
      <label>Rating<input name="rating" type="number" min="0" max="5" step="0.1" placeholder="Annual review only" /></label>
      <label>Review period start<input name="review_period_start" type="date" /></label>
      <label>Review period end<input name="review_period_end" type="date" /></label>
      <label className="span-2">Subject<input name="subject" required placeholder="Memo / infraction / review title" /></label>
      <label className="span-2">Details<textarea name="details" rows={4} placeholder="Details, action required, supervisor note, or review comments" /></label>
      <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : "Save HR record"}</button>
      {message ? <p className="muted">{message}</p> : null}
    </form>
  );
}
