"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Props = {
  employeeId: number;
};

export function PerformanceLogForm({ employeeId }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");

    const body = {
      employee_id: employeeId,
      log_date: String(formData.get("log_date") || new Date().toISOString().slice(0, 10)),
      category: String(formData.get("category") || "Neutral"),
      area: String(formData.get("area") || "General"),
      severity: String(formData.get("severity") || "Low"),
      note: String(formData.get("note") || ""),
      private_note: String(formData.get("private_note") || "") || null,
      evidence_ref: String(formData.get("evidence_ref") || "") || null,
      is_general: formData.get("is_general") ? 1 : 0,
    };

    const response = await fetch("/api/performance/logs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await response.json().catch(() => ({}));
    setBusy(false);

    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Performance note was not saved.");
      return;
    }

    setOpen(false);
    router.refresh();
  }

  if (!open) {
    return <button className="primary-button" type="button" onClick={() => setOpen(true)}>Add Performance Note</button>;
  }

  return (
    <form action={submit} className="card review-form">
      <strong>Performance Note</strong>

      <div className="review-form-grid">
        <label>Date<input name="log_date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} /></label>
        <label>
          Category
          <select name="category" defaultValue="Neutral">
            <option>Positive</option>
            <option>Concern</option>
            <option>Neutral</option>
            <option>General</option>
          </select>
        </label>
        <label>
          Area
          <select name="area" defaultValue="General">
            <option>General</option>
            <option>Attendance</option>
            <option>Guest Service</option>
            <option>SOP</option>
            <option>Teamwork</option>
            <option>Cleanliness</option>
            <option>Reliability</option>
            <option>Initiative</option>
            <option>Communication</option>
            <option>Other</option>
          </select>
        </label>
        <label>
          Severity
          <select name="severity" defaultValue="Low">
            <option>Low</option>
            <option>Medium</option>
            <option>High</option>
          </select>
        </label>
      </div>

      <label>Note<textarea name="note" rows={3} required placeholder="What happened? Be factual and specific." /></label>
      <label>Private management note<textarea name="private_note" rows={2} placeholder="Optional internal context." /></label>
      <label>Evidence / attachment reference<input name="evidence_ref" placeholder="Optional file/link/reference." /></label>
      <label className="review-check"><input name="is_general" type="checkbox" /> General observation</label>

      <div className="badge-row">
        <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : "Save note"}</button>
        <button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button>
      </div>

      {message ? <p className="footer-note">{message}</p> : null}
    </form>
  );
}
