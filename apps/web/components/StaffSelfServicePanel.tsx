"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  StaffSchedulePublication,
  StaffShift,
  StaffShiftRequest,
  StaffCoworkerShift,
  StaffShiftRequests,
} from "@/components/StaffShiftRequests";

type Employee = { id: number; name: string; employee_code?: string; department: string; position?: string };
type LeaveBalance = { leave_type_id: number; leave_type_name: string; credits: number; used: number; pending: number; remaining: number | null; paid: number };
type LeaveRequest = { id: number; leave_type_name: string; start_date: string; end_date: string; days: number; status: string; reason?: string; decision_note?: string | null };
type HrRecord = { id: number; record_date: string; record_type: string; subject: string; severity: string; status: string; issued_by?: string | null };
type Attendance = { work_date: string; actual_in?: string | null; actual_out?: string | null; attendance_status: string; is_absent: number; absence_type?: string | null; approved_ot_hours?: number; notes?: string | null };
type CashAdvance = { id: number; advance_date: string; amount: number; remaining_balance: number; status: string; repayment_method?: string; deduction_per_payroll?: number };

type SelfServiceData = {
  employee: Employee | null;
  schedule: StaffShift[];
  requests: StaffShiftRequest[];
  coworker_shifts: StaffCoworkerShift[];
  publications: StaffSchedulePublication[];
  leave_balances: LeaveBalance[];
  leave_requests: LeaveRequest[];
  hr_records: HrRecord[];
  attendance: Attendance[];
  cash_advances: CashAdvance[];
};

function money(value: number) {
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(Number(value || 0));
}

export function StaffSelfServicePanel() {
  const [data, setData] = useState<SelfServiceData | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    const response = await fetch("/api/schedule/shifts", { cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || body.message || "Self-service could not be loaded.");
    setData(body as SelfServiceData);
  }, []);

  useEffect(() => {
    void load().catch((reason) => setError(reason instanceof Error ? reason.message : "Self-service could not be loaded."));
  }, [load]);

  async function submitLeave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/schedule/shifts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operation: "leave_request",
        leave_type_id: Number(fields.get("leave_type_id")),
        start_date: String(fields.get("start_date") || ""),
        end_date: String(fields.get("end_date") || ""),
        reason: String(fields.get("reason") || ""),
      }),
    });
    const body = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage(body.detail || "Leave request failed.");
      return;
    }
    form.reset();
    setMessage("Leave request submitted.");
    await load();
  }

  async function withdrawLeave(requestId: number) {
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/schedule/shifts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation: "withdraw_leave_request", request_id: requestId }),
    });
    const body = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage(body.detail || "Leave request could not be withdrawn.");
      return;
    }
    setMessage("Leave request withdrawn.");
    await load();
  }

  if (error) return <section className="card"><strong>Self-service unavailable</strong><p className="muted">{error}</p><button className="button small" type="button" onClick={() => void load()}>Retry</button></section>;
  if (!data) return <section className="card"><p className="muted">Loading...</p></section>;
  if (!data.employee) return <section className="card"><strong>Employee account not linked</strong></section>;

  return (
    <>
      <StaffShiftRequests
        employeeId={data.employee.id}
        schedule={data.schedule || []}
        requests={data.requests || []}
        coworkerShifts={data.coworker_shifts || []}
        publications={data.publications || []}
        onChanged={load}
      />

      <section className="grid cols-2">
        <div className="card">
          <div className="panel-title"><h2>Leave balances</h2></div>
          {(data.leave_balances || []).map((item) => <p key={item.leave_type_id}><strong>{item.leave_type_name}</strong><br /><span className="muted">{item.paid ? `${Number(item.remaining || 0).toLocaleString("en-PH")} available · ${Number(item.pending || 0).toLocaleString("en-PH")} pending · ${Number(item.credits || 0).toLocaleString("en-PH")} total` : "Unpaid"}</span></p>)}
          {!data.leave_balances?.length ? <p className="muted">No leave balances.</p> : null}
        </div>
        <div className="card">
          <div className="panel-title"><h2>Request leave</h2></div>
          <form className="form-grid" onSubmit={submitLeave}>
            <label>Leave type<select name="leave_type_id" required defaultValue=""><option value="" disabled>Select</option>{data.leave_balances.map((item) => <option value={item.leave_type_id} key={item.leave_type_id}>{item.leave_type_name}</option>)}</select></label>
            <label>Start<input name="start_date" type="date" required /></label>
            <label>End<input name="end_date" type="date" required /></label>
            <label>Reason<textarea name="reason" rows={3} minLength={3} required /></label>
            <button className="button" type="submit" disabled={busy}>Submit</button>
          </form>
          {message ? <p className="muted">{message}</p> : null}
        </div>
      </section>

      <section className="card">
        <div className="panel-title"><h2>Leave requests</h2></div>
        <div className="table-wrap"><table><thead><tr><th>Type</th><th>Dates</th><th>Days</th><th>Status</th><th>Reason</th><th>Action</th></tr></thead><tbody>
          {data.leave_requests.map((item) => <tr key={item.id}><td>{item.leave_type_name}</td><td>{item.start_date} to {item.end_date}</td><td>{item.days}</td><td>{item.status}{item.decision_note ? <><br /><span className="muted">{item.decision_note}</span></> : null}</td><td>{item.reason || "—"}</td><td>{item.status === "Pending" ? <button className="button small secondary" type="button" disabled={busy} onClick={() => void withdrawLeave(item.id)}>Withdraw</button> : "—"}</td></tr>)}
          {!data.leave_requests.length ? <tr><td colSpan={6}>No leave requests.</td></tr> : null}
        </tbody></table></div>
      </section>

      <section className="grid cols-2">
        <div className="card">
          <div className="panel-title"><h2>Attendance</h2></div>
          <div className="table-wrap"><table><thead><tr><th>Date</th><th>Time</th><th>Status</th><th>OT</th></tr></thead><tbody>
            {data.attendance.map((item, index) => <tr key={`${item.work_date}-${index}`}><td>{item.work_date}</td><td>{item.is_absent ? item.absence_type || "Absent" : `${item.actual_in || "—"}–${item.actual_out || "—"}`}</td><td>{item.attendance_status}</td><td>{Number(item.approved_ot_hours || 0).toLocaleString("en-PH")}</td></tr>)}
            {!data.attendance.length ? <tr><td colSpan={4}>No attendance records.</td></tr> : null}
          </tbody></table></div>
        </div>
        <div className="card">
          <div className="panel-title"><h2>Cash advances</h2></div>
          {data.cash_advances.map((item) => <p key={item.id}><strong>{money(item.remaining_balance)} remaining</strong><br /><span className="muted">{item.advance_date} · {item.status} · original {money(item.amount)}</span></p>)}
          {!data.cash_advances.length ? <p className="muted">No cash advances.</p> : null}
        </div>
      </section>

      <section className="card">
        <div className="panel-title"><h2>HR records</h2></div>
        {data.hr_records.map((item) => <p key={item.id}><strong>{item.record_date} · {item.record_type}</strong><br />{item.subject}<br /><span className="muted">{item.status} · {item.severity}{item.issued_by ? ` · ${item.issued_by}` : ""}</span></p>)}
        {!data.hr_records.length ? <p className="muted">No HR records.</p> : null}
      </section>
    </>
  );
}
