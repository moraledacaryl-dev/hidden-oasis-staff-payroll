"use client";

import { FormEvent, useMemo, useState } from "react";
import { shiftRequestTypes } from "@/app/me/shift-request-types";

export type StaffShift = { id: number; shift_date: string; start_time: string; end_time: string; position?: string; department?: string; status?: string; notes?: string; week_start?: string };
export type StaffCoworkerShift = { id: number; employee_id: number; full_name: string; shift_date: string; start_time: string; end_time: string; position?: string };
export type StaffShiftRequest = { id: number; request_no: string; employee_id: number; request_type: string; original_date: string; original_start_time: string; original_end_time: string; requested_date?: string | null; requested_start_time?: string | null; requested_end_time?: string | null; reason: string; proposed_swap_employee_id?: number | null; proposed_swap_shift_id?: number | null; swap_employee_name?: string | null; status: string; submitted_at: string; decision_note?: string | null; has_attachment?: boolean };
export type StaffSchedulePublication = { week_start: string; published_at?: string | null; published_by?: string | null; notes?: string | null; acknowledged: boolean; acknowledged_at?: string | null };

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

async function uploadAttachment(requestId: number, file: File) {
  const form = new FormData();
  form.set("request_id", String(requestId));
  form.set("file", file);
  const response = await fetch("/api/schedule/shifts", { method: "POST", body: form });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || "Attachment upload failed.");
}

function todayIso() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function sortAscending(a: StaffShift, b: StaffShift) {
  return `${a.shift_date} ${a.start_time}`.localeCompare(`${b.shift_date} ${b.start_time}`);
}

function ScheduleTable({ items, emptyText }: { items: StaffShift[]; emptyText: string }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Date</th><th>Time</th><th>Position</th><th>Department</th><th>Status</th><th>Notes</th></tr></thead>
        <tbody>
          {items.map((shift) => <tr key={`${shift.id}-${shift.shift_date}-${shift.start_time}`}><td>{shift.shift_date}</td><td><strong>{shift.start_time}–{shift.end_time}</strong></td><td>{shift.position || "—"}</td><td>{shift.department || "—"}</td><td>{shift.status || "—"}</td><td>{shift.notes || "—"}</td></tr>)}
          {!items.length ? <tr><td colSpan={6}>{emptyText}</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}

export function StaffShiftRequests({ employeeId, schedule, requests, coworkerShifts, publications, onChanged }: { employeeId: number; schedule: StaffShift[]; requests: StaffShiftRequest[]; coworkerShifts: StaffCoworkerShift[]; publications: StaffSchedulePublication[]; onChanged: () => Promise<void> }) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const { upcomingSchedule, previousSchedule } = useMemo(() => {
    const today = todayIso();
    const ordered = [...schedule].sort(sortAscending);
    return {
      upcomingSchedule: ordered.filter((shift) => shift.shift_date >= today),
      previousSchedule: ordered.filter((shift) => shift.shift_date < today).reverse(),
    };
  }, [schedule]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const swapShiftId = Number(form.get("proposed_swap_shift_id") || 0) || null;
    const swapShift = coworkerShifts.find((item) => item.id === swapShiftId);
    try {
      const data = await post({
        operation: "staff_request",
        shift_id: Number(form.get("shift_id")),
        request_type: String(form.get("request_type") || ""),
        requested_date: String(form.get("requested_date") || "") || null,
        requested_start_time: String(form.get("requested_start_time") || "") || null,
        requested_end_time: String(form.get("requested_end_time") || "") || null,
        reason: String(form.get("reason") || ""),
        proposed_swap_employee_id: swapShift?.employee_id || null,
        proposed_swap_shift_id: swapShiftId,
        emergency: form.get("emergency") === "on",
        accuracy_confirmed: form.get("accuracy_confirmed") === "on",
      });
      const file = form.get("attachment");
      if (file instanceof File && file.size > 0) await uploadAttachment(Number(data.request_id), file);
      setMessage(`Request ${data.request_no} submitted.`);
      formElement.reset();
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function act(operation: "withdraw_request" | "confirm_swap" | "decline_swap", requestId: number) {
    setBusy(true);
    setMessage("");
    try {
      await post({ operation, request_id: requestId });
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function acknowledge(weekStart: string) {
    setBusy(true);
    setMessage("");
    try {
      await post({ operation: "acknowledge_schedule", week_start: weekStart });
      setMessage(`Schedule for week of ${weekStart} acknowledged.`);
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Acknowledgement failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="card staff-schedule-print">
        <div className="panel-title"><h2>My schedule</h2><button className="button secondary print-actions" type="button" onClick={() => window.print()}>Print / Save PDF</button></div>
        {publications.length ? <div className="badge-row print-actions">{publications.map((publication) => publication.acknowledged ? <span className="badge" key={publication.week_start}>Week of {publication.week_start} acknowledged{publication.acknowledged_at ? ` · ${publication.acknowledged_at}` : ""}</span> : <button className="button small" disabled={busy} key={publication.week_start} type="button" onClick={() => acknowledge(publication.week_start)}>Acknowledge week of {publication.week_start}</button>)}</div> : null}

        <div className="panel-title"><h3>Upcoming</h3><span className="badge">{upcomingSchedule.length}</span></div>
        <ScheduleTable items={upcomingSchedule} emptyText="No upcoming published shifts." />

        <details className="print-actions" style={{ marginTop: "1rem" }}>
          <summary><strong>Previous schedules</strong> <span className="muted">({previousSchedule.length})</span></summary>
          <div style={{ marginTop: "0.75rem" }}><ScheduleTable items={previousSchedule} emptyText="No previous published shifts." /></div>
        </details>
        <div className="print-only" style={{ marginTop: "1rem" }}>
          <div className="panel-title"><div><h3>Previous schedules</h3></div></div>
          <ScheduleTable items={previousSchedule} emptyText="No previous published shifts." />
        </div>
      </section>

      <section className="card">
        <div className="panel-title"><h2>Request a shift change</h2></div>
        {message ? <p><strong>{message}</strong></p> : null}
        <form onSubmit={submit} className="grid cols-2">
          <label className="field">Affected shift<select name="shift_id" required defaultValue=""><option value="" disabled>Select your upcoming shift</option>{upcomingSchedule.map((shift) => <option key={shift.id} value={shift.id}>{shift.shift_date} · {shift.start_time}–{shift.end_time}</option>)}</select></label>
          <label className="field">Request type<select name="request_type" required defaultValue={shiftRequestTypes[0]}>{shiftRequestTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
          <label className="field">Requested date<input type="date" name="requested_date" /></label>
          <div className="grid cols-2"><label className="field">New start<input type="time" name="requested_start_time" /></label><label className="field">New end<input type="time" name="requested_end_time" /></label></div>
          <label className="field">Shift to swap with<select name="proposed_swap_shift_id" defaultValue=""><option value="">Not a swap</option>{coworkerShifts.map((shift) => <option key={shift.id} value={shift.id}>{shift.shift_date} · {shift.start_time}–{shift.end_time} · {shift.full_name}</option>)}</select></label>
          <label className="field">Supporting document<input type="file" name="attachment" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" style={{ width: "100%", minWidth: 0, maxWidth: "100%", fontSize: "0.72rem", overflow: "hidden" }} /><span className="muted" style={{ display: "block", maxWidth: "100%", overflowWrap: "anywhere", lineHeight: 1.25 }}>Optional attachment up to 10 MB.</span></label>
          <label className="field" style={{ gridColumn: "1 / -1" }}>Reason<textarea name="reason" rows={4} required minLength={3} /></label>
          <label className="field"><span><input type="checkbox" name="emergency" /> Emergency review priority</span></label>
          <label className="field"><span><input type="checkbox" name="accuracy_confirmed" required /> I confirm that this information is accurate.</span></label>
          <div><button className="button" type="submit" disabled={busy || !upcomingSchedule.length}>{busy ? "Saving…" : "Submit request"}</button></div>
        </form>
      </section>

      <section className="card">
        <div className="panel-title"><h2>My requests</h2></div>
        <div className="table-wrap"><table><thead><tr><th>Request</th><th>Original</th><th>Requested</th><th>Reason</th><th>Status</th><th>Action</th></tr></thead><tbody>
          {requests.map((item) => {
            const waitingForMe = item.proposed_swap_employee_id === employeeId && item.status === "Swap Confirmation";
            const canWithdraw = item.employee_id === employeeId && ["Pending", "Swap Confirmation", "Emergency Review"].includes(item.status);
            return <tr key={item.id}><td><strong>{item.request_no}</strong><br /><span className="muted">{item.request_type} · {item.submitted_at}</span>{item.has_attachment ? <><br /><span className="muted">Attachment uploaded</span></> : null}</td><td>{item.original_date}<br />{item.original_start_time}–{item.original_end_time}</td><td>{item.requested_date || "Same date"}<br />{item.requested_start_time || item.original_start_time}–{item.requested_end_time || item.original_end_time}{item.swap_employee_name ? <><br /><span className="muted">Swap: {item.swap_employee_name}</span></> : null}</td><td>{item.reason}</td><td><strong>{item.status}</strong>{item.decision_note ? <><br /><span className="muted">{item.decision_note}</span></> : null}</td><td>{waitingForMe ? <><button className="button small" disabled={busy} onClick={() => act("confirm_swap", item.id)}>Confirm swap</button><button className="button small secondary" disabled={busy} onClick={() => act("decline_swap", item.id)}>Decline swap</button></> : null}{canWithdraw ? <button className="button small secondary" disabled={busy} onClick={() => act("withdraw_request", item.id)}>Withdraw</button> : null}</td></tr>;
          })}
          {!requests.length ? <tr><td colSpan={6}>No requests submitted.</td></tr> : null}
        </tbody></table></div>
      </section>
    </>
  );
}
