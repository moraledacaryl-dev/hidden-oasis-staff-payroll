"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { shiftRequestTypes } from "@/app/me/shift-request-types";

export type StaffShift = { id: number; shift_date: string; start_time: string; end_time: string; position?: string; department?: string; status?: string; notes?: string };
export type StaffCoworker = { id: number; full_name: string; department?: string };
export type StaffShiftRequest = { id: number; request_no: string; employee_id: number; request_type: string; original_date: string; original_start_time: string; original_end_time: string; requested_date?: string | null; requested_start_time?: string | null; requested_end_time?: string | null; reason: string; proposed_swap_employee_id?: number | null; swap_employee_name?: string | null; status: string; submitted_at: string; decision_note?: string | null };

async function post(body: Record<string, unknown>) {
  const response = await fetch("/api/schedule/shifts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || "Request failed.");
  return data;
}

export function StaffShiftRequests({ employeeId, schedule, requests, coworkers }: { employeeId: number; schedule: StaffShift[]; requests: StaffShiftRequest[]; coworkers: StaffCoworker[] }) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const data = await post({
        operation: "staff_request",
        shift_id: Number(form.get("shift_id")),
        request_type: String(form.get("request_type") || ""),
        requested_date: String(form.get("requested_date") || "") || null,
        requested_start_time: String(form.get("requested_start_time") || "") || null,
        requested_end_time: String(form.get("requested_end_time") || "") || null,
        reason: String(form.get("reason") || ""),
        proposed_swap_employee_id: Number(form.get("proposed_swap_employee_id") || 0) || null,
        emergency: form.get("emergency") === "on",
        accuracy_confirmed: form.get("accuracy_confirmed") === "on",
      });
      setMessage(`Request ${data.request_no} submitted.`);
      event.currentTarget.reset();
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function act(operation: "withdraw_request" | "confirm_swap", requestId: number) {
    setBusy(true);
    setMessage("");
    try {
      await post({ operation, request_id: requestId });
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="card">
        <div className="panel-title"><div><h2>My schedule</h2><p className="muted">Only shifts linked to your employee account are shown.</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>Date</th><th>Time</th><th>Position</th><th>Department</th><th>Status</th><th>Notes</th></tr></thead><tbody>
          {schedule.map((shift) => <tr key={shift.id}><td>{shift.shift_date}</td><td><strong>{shift.start_time}–{shift.end_time}</strong></td><td>{shift.position || "—"}</td><td>{shift.department || "—"}</td><td>{shift.status || "—"}</td><td>{shift.notes || "—"}</td></tr>)}
          {!schedule.length ? <tr><td colSpan={6}>No schedule available.</td></tr> : null}
        </tbody></table></div>
      </section>

      <section className="card">
        <div className="panel-title"><div><h2>Request a shift change</h2><p className="muted">Online submission is the official record. The original request stays in history.</p></div></div>
        {message ? <p><strong>{message}</strong></p> : null}
        <form onSubmit={submit} className="grid cols-2">
          <label className="field">Affected shift<select name="shift_id" required defaultValue=""><option value="" disabled>Select your shift</option>{schedule.map((shift) => <option key={shift.id} value={shift.id}>{shift.shift_date} · {shift.start_time}–{shift.end_time}</option>)}</select></label>
          <label className="field">Request type<select name="request_type" required defaultValue={shiftRequestTypes[0]}>{shiftRequestTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
          <label className="field">Requested date<input type="date" name="requested_date" /></label>
          <div className="grid cols-2"><label className="field">New start<input type="time" name="requested_start_time" /></label><label className="field">New end<input type="time" name="requested_end_time" /></label></div>
          <label className="field">Proposed swap employee<select name="proposed_swap_employee_id" defaultValue=""><option value="">Not a swap</option>{coworkers.map((person) => <option key={person.id} value={person.id}>{person.full_name} · {person.department || "Unassigned"}</option>)}</select></label>
          <label className="field" style={{ gridColumn: "1 / -1" }}>Reason<textarea name="reason" rows={4} required minLength={3} /></label>
          <label className="field"><span><input type="checkbox" name="emergency" /> Emergency review priority</span></label>
          <label className="field"><span><input type="checkbox" name="accuracy_confirmed" required /> I confirm that this information is accurate.</span></label>
          <div><button className="button" type="submit" disabled={busy}>{busy ? "Saving…" : "Submit request"}</button></div>
        </form>
      </section>

      <section className="card">
        <div className="panel-title"><div><h2>My requests</h2><p className="muted">Pending requests may be withdrawn, but are never erased.</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>Request</th><th>Original</th><th>Requested</th><th>Reason</th><th>Status</th><th>Action</th></tr></thead><tbody>
          {requests.map((item) => {
            const waitingForMe = item.proposed_swap_employee_id === employeeId && item.status === "Swap Confirmation";
            const canWithdraw = item.employee_id === employeeId && ["Pending", "Swap Confirmation", "Emergency Review"].includes(item.status);
            return <tr key={item.id}><td><strong>{item.request_no}</strong><br /><span className="muted">{item.request_type} · {item.submitted_at}</span></td><td>{item.original_date}<br />{item.original_start_time}–{item.original_end_time}</td><td>{item.requested_date || "Same date"}<br />{item.requested_start_time || item.original_start_time}–{item.requested_end_time || item.original_end_time}{item.swap_employee_name ? <><br /><span className="muted">Swap: {item.swap_employee_name}</span></> : null}</td><td>{item.reason}</td><td><strong>{item.status}</strong>{item.decision_note ? <><br /><span className="muted">{item.decision_note}</span></> : null}</td><td>{waitingForMe ? <button className="button small" disabled={busy} onClick={() => act("confirm_swap", item.id)}>Confirm swap</button> : null}{canWithdraw ? <button className="button small secondary" disabled={busy} onClick={() => act("withdraw_request", item.id)}>Withdraw</button> : null}</td></tr>;
          })}
          {!requests.length ? <tr><td colSpan={6}>No requests submitted.</td></tr> : null}
        </tbody></table></div>
      </section>
    </>
  );
}
