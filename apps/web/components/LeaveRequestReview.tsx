"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export type LeaveRequestItem = {
  id: number;
  employee_name: string;
  leave_type_name?: string;
  start_date: string;
  end_date: string;
  days: number;
  reason?: string;
  status: string;
  reviewed_by?: string | null;
  decision_note?: string | null;
};

export function LeaveRequestReview({ items }: { items: LeaveRequestItem[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [notes, setNotes] = useState<Record<number, string>>({});

  async function decide(item: LeaveRequestItem, status: "Approved" | "Rejected") {
    setBusy(item.id);
    setMessage("");
    const response = await fetch("/api/hr/leave-requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: item.id, status, decision_note: notes[item.id] || "" }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok) {
      setMessage(data.detail || "Leave request could not be updated.");
      return;
    }
    router.refresh();
  }

  return (
    <section className="card">
      <div className="panel-title"><h2>Leave requests</h2></div>
      {message ? <p className="muted">{message}</p> : null}
      <div className="table-wrap"><table><thead><tr><th>Employee</th><th>Type</th><th>Dates</th><th>Days</th><th>Reason</th><th>Status</th><th>Decision</th></tr></thead><tbody>
        {items.map((item) => <tr key={item.id}><td>{item.employee_name}</td><td>{item.leave_type_name || "Leave"}</td><td>{item.start_date} to {item.end_date}</td><td>{item.days}</td><td>{item.reason || "—"}</td><td>{item.status}{item.decision_note ? <><br /><span className="muted">{item.decision_note}</span></> : null}</td><td>{item.status === "Pending" ? <div className="grid"><input aria-label={`Decision note for ${item.employee_name}`} placeholder="Decision note" value={notes[item.id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [item.id]: event.target.value }))} /><div className="action-row"><button className="button small" disabled={busy === item.id} onClick={() => decide(item, "Approved")}>Approve</button><button className="button small secondary" disabled={busy === item.id} onClick={() => decide(item, "Rejected")}>Reject</button></div></div> : item.reviewed_by || "—"}</td></tr>)}
        {!items.length ? <tr><td colSpan={7}>No leave requests.</td></tr> : null}
      </tbody></table></div>
    </section>
  );
}
