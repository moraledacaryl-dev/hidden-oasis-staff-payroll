"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { ScheduleEmployee, ScheduleShift } from "@/lib/schedule-types";

const positions = ["Receptionist", "Cook", "Barista", "Bartender", "Security", "Housekeeper", "Other"];
const leaveKinds = [
  "None",
  "SIL",
  "Sick Leave",
  "Vacation Leave",
  "Emergency Leave",
  "Bereavement Leave",
  "Official Business",
  "Other Approved Absence",
  "Approved / Excused Absence",
  "Unexcused Absence",
  "AWOL",
];
const noticeTimings = ["In advance", "At least 1 hour before shift", "After shift start", "No notice"];
const attendanceStatuses = ["Pending", "Approved", "Needs Review", "Needs Correction", "Rejected"];

type TabKey = "scheduled" | "actual" | "leave";
type Bundle = {
  ok: boolean;
  employee?: ScheduleEmployee | null;
  shift?: ScheduleShift | null;
  actual?: { id: number; actual_in?: string | null; actual_out?: string | null; attendance_status?: string | null; approved_ot_hours?: number | null; notes?: string | null; is_absent?: number | null; absence_type?: string | null; notice_given_at?: string | null; notice_timing?: string | null; evidence_ref?: string | null } | null;
  leave?: { id: number; leave_type_name?: string | null; reason?: string | null; paid?: number | null; status?: string | null; days?: number | null; paid_hours?: number | null } | null;
  payroll_locked?: boolean;
  paid_run?: { id: number; period_start: string; period_end: string } | null;
  legacy_read_only?: boolean;
  message?: string | null;
};

type Props = {
  open: boolean;
  day: string;
  shift: ScheduleShift | null;
  initialEmployeeId?: number | null;
  initialTab?: TabKey;
  employees: ScheduleEmployee[];
  canEdit: boolean;
  onClose: () => void;
};

function emptyBundle(): Bundle {
  return { ok: true, shift: null, actual: null, leave: null };
}

export function ScheduleDayEditorModal({ open, day, shift, initialEmployeeId = null, initialTab = "scheduled", employees, canEdit, onClose }: Props) {
  const router = useRouter();
  const [tab, setTab] = useState<TabKey>(initialTab);
  const [bundle, setBundle] = useState<Bundle>(emptyBundle());
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const initialEmployeeIdValue = shift?.employee_id ? String(shift.employee_id) : (initialEmployeeId ? String(initialEmployeeId) : "");
  const [employeeId, setEmployeeId] = useState(initialEmployeeIdValue);
  const [shiftDate, setShiftDate] = useState(day);

  useEffect(() => {
    if (!open) return;
    setTab(initialTab);
    setMessage("");
    setEmployeeId(shift?.employee_id ? String(shift.employee_id) : (initialEmployeeId ? String(initialEmployeeId) : ""));
    setShiftDate(shift?.shift_date || day);
    const params = new URLSearchParams();
    params.set("shift_date", shift?.shift_date || day);
    if (shift?.id) params.set("shift_id", String(shift.id));
    else if (shift?.employee_id || initialEmployeeId) params.set("employee_id", String(shift?.employee_id || initialEmployeeId));
    if (!shift?.id && !shift?.employee_id && !initialEmployeeId) {
      setBundle(emptyBundle());
      return;
    }
    fetch(`/api/schedule/day?${params.toString()}`)
      .then((res) => res.json())
      .then((data) => {
        setBundle(data);
        if (data.leave) setTab("leave");
      })
      .catch(() => setMessage("Could not load employee-day details."));
  }, [day, initialEmployeeId, initialTab, open, shift]);

  const currentShift = bundle.shift || shift;
  const selectedEmployee = useMemo(() => employees.find((item) => String(item.id) === employeeId), [employeeId, employees]);
  const readOnly = !canEdit;
  const lockedSnapshot = Boolean(bundle.payroll_locked);
  const hasLeave = Boolean(bundle.leave);

  useEffect(() => {
    if (hasLeave && tab !== "leave") setTab("leave");
  }, [hasLeave, tab]);

  if (!open) return null;

  async function save(section: TabKey, payload: Record<string, unknown>) {
    if (hasLeave && section !== "leave") {
      setMessage("Clear the day first before adding a shift or actual attendance.");
      setTab("leave");
      return;
    }
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/schedule/day", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section, ...payload }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Not saved.");
      return;
    }
    setBundle(data);
    setTab(data.leave ? "leave" : section);
    setMessage(data.message || "Saved.");
    router.refresh();
  }

  async function clearDay() {
    if (!employeeId) return;
    if (!window.confirm("Clear this entire day? This removes the shift, actual attendance, leave or absence, and rest-day marker so you can choose again.")) return;
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/schedule/day", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        section: "reset",
        employee_id: Number(employeeId),
        work_date: shiftDate,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Day was not cleared.");
      return;
    }
    setBundle(emptyBundle());
    router.refresh();
    onClose();
  }

  async function deleteShift() {
    if (!currentShift?.id) return;
    if (!window.confirm("Delete this scheduled shift? Existing saved payroll runs will not change unless you save a revision.")) return;
    setBusy(true);
    const response = await fetch("/api/schedule/day", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section: "remove", shift_id: currentShift.id }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Shift was not deleted.");
      return;
    }
    setMessage("Shift deleted.");
    router.refresh();
    onClose();
  }

  function saveScheduled(formData: FormData) {
    void save("scheduled", {
      shift_id: currentShift?.id || null,
      employee_id: Number(formData.get("employee_id") || 0) || null,
      shift_date: String(formData.get("shift_date") || shiftDate),
      start_time: String(formData.get("start_time") || "08:00"),
      end_time: String(formData.get("end_time") || "17:00"),
      position: String(formData.get("position") || "Other"),
      department: String(formData.get("department") || "") || null,
      break_minutes: Number(formData.get("break_minutes") || 0),
      notes: String(formData.get("notes") || "") || null,
    });
  }

  function saveActual(formData: FormData) {
    if (!employeeId) {
      setMessage("Choose an employee before saving actual attendance.");
      return;
    }
    void save("actual", {
      employee_id: Number(employeeId),
      shift_date: shiftDate,
      actual_in: String(formData.get("actual_in") || "") || null,
      actual_out: String(formData.get("actual_out") || "") || null,
      attendance_status: String(formData.get("attendance_status") || "Pending"),
      approved_ot_hours: Number(formData.get("approved_ot_hours") || 0),
      notes: String(formData.get("notes") || "") || null,
    });
  }

  function saveLeave(formData: FormData) {
    if (!employeeId) {
      setMessage("Choose an employee before saving leave or absence.");
      return;
    }
    const rawHours = String(formData.get("leave_hours") || "").trim();
    void save("leave", {
      employee_id: Number(employeeId),
      shift_date: shiftDate,
      leave_kind: String(formData.get("leave_kind") || "None"),
      leave_days: rawHours ? null : Number(formData.get("leave_days") || 1),
      leave_hours: rawHours ? Number(rawHours) : null,
      reason: String(formData.get("reason") || "") || null,
      notice_given_at: String(formData.get("notice_given_at") || "") || null,
      notice_timing: String(formData.get("notice_timing") || "") || null,
      evidence_ref: String(formData.get("evidence_ref") || "") || null,
    });
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-panel schedule-modal">
        <div className="panel-title">
          <div>
            <span className="eyebrow">Employee day</span>
            <h2>{selectedEmployee?.full_name || currentShift?.employee_name || "Schedule day"} · {shiftDate}</h2>
            {hasLeave ? <p className="muted">This day is marked as leave. Clear the entire day to choose Add shift, Rest day, or Leave again.</p> : null}
            {lockedSnapshot ? <p className="muted">This date belongs to saved payroll run #{bundle.paid_run?.id}. You can edit it here; the saved payroll run will stay unchanged until you save a revised run.</p> : null}
            {bundle.message ? <p className="muted">{bundle.message}</p> : null}
          </div>
          <button className="button small ghost" type="button" onClick={onClose}>Close</button>
        </div>

        <div className="tabs">
          {!hasLeave ? <button className={tab === "scheduled" ? "tab active" : "tab"} type="button" onClick={() => setTab("scheduled")}>Scheduled</button> : null}
          {!hasLeave ? <button className={tab === "actual" ? "tab active" : "tab"} type="button" onClick={() => setTab("actual")}>Actual</button> : null}
          <button className={tab === "leave" ? "tab active" : "tab"} type="button" onClick={() => setTab("leave")}>Leave / Absence</button>
        </div>

        {!hasLeave && tab === "scheduled" ? (
          <form action={saveScheduled} className="form-grid modal-form">
            <label>Date<input name="shift_date" type="date" value={shiftDate} disabled={readOnly} onChange={(event) => setShiftDate(event.target.value)} required /></label>
            <label>Person<select name="employee_id" value={employeeId} disabled={readOnly} onChange={(event) => setEmployeeId(event.target.value)}><option value="">Unassigned</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
            <label>Start<input name="start_time" type="time" defaultValue={currentShift?.start_time || "08:00"} disabled={readOnly} required /></label>
            <label>End<input name="end_time" type="time" defaultValue={currentShift?.end_time || "17:00"} disabled={readOnly} required /></label>
            <label>Role<select name="position" defaultValue={currentShift?.position || selectedEmployee?.position || "Other"} disabled={readOnly}>{positions.map((p) => <option key={p} value={p}>{p}</option>)}</select></label>
            <label>Dept<input name="department" defaultValue={currentShift?.employee_department || currentShift?.department || selectedEmployee?.department || ""} disabled={readOnly} /></label>
            <label>Break<input name="break_minutes" type="number" min="0" defaultValue={currentShift?.break_minutes ?? 60} disabled={readOnly} /></label>
            <label>Note<input name="notes" defaultValue={currentShift?.notes || ""} disabled={readOnly} /></label>
            {canEdit ? <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : "Save scheduled shift"}</button> : null}
            {canEdit && currentShift?.id ? <button className="button ghost" type="button" disabled={busy} onClick={deleteShift}>Delete shift</button> : null}
          </form>
        ) : null}

        {!hasLeave && tab === "actual" ? (
          <form action={saveActual} className="form-grid modal-form">
            <label>Employee<select value={employeeId} disabled={readOnly} onChange={(event) => setEmployeeId(event.target.value)}><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
            <label>Actual in<input name="actual_in" type="time" defaultValue={bundle.actual?.actual_in || ""} disabled={readOnly} /></label>
            <label>Actual out<input name="actual_out" type="time" defaultValue={bundle.actual?.actual_out || ""} disabled={readOnly} /></label>
            <label>Status<select name="attendance_status" defaultValue={bundle.actual?.attendance_status || "Pending"} disabled={readOnly}>{attendanceStatuses.map((status) => <option key={status}>{status}</option>)}</select></label>
            <label>Approved OT<input name="approved_ot_hours" type="number" min="0" step="0.25" defaultValue={bundle.actual?.approved_ot_hours ?? 0} disabled={readOnly} /></label>
            <label>Admin note<input name="notes" defaultValue={bundle.actual?.notes || ""} disabled={readOnly} /></label>
            {canEdit ? <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : "Save actual"}</button> : null}
          </form>
        ) : null}

        {tab === "leave" ? (
          <form action={saveLeave} className="form-grid modal-form">
            <label>Employee<select value={employeeId} disabled={readOnly || lockedSnapshot || hasLeave} onChange={(event) => setEmployeeId(event.target.value)}><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
            <label>Type<select name="leave_kind" defaultValue={bundle.leave?.leave_type_name || bundle.actual?.absence_type || "None"} disabled={readOnly || lockedSnapshot}>{leaveKinds.map((kind) => <option key={kind}>{kind}</option>)}</select></label>
            <label>Days<input name="leave_days" type="number" min="0.25" step="0.25" defaultValue={bundle.leave?.days ?? 1} disabled={readOnly || lockedSnapshot} /></label>
            <label>Hours, if partial<input name="leave_hours" type="number" min="0" step="0.25" defaultValue={bundle.leave?.paid_hours ?? ""} disabled={readOnly || lockedSnapshot} /></label>
            <label>Date informed<input name="notice_given_at" type="datetime-local" defaultValue={bundle.actual?.notice_given_at ? String(bundle.actual.notice_given_at).replace(" ", "T").slice(0, 16) : ""} disabled={readOnly || lockedSnapshot} /></label>
            <label>Notice timing<select name="notice_timing" defaultValue={bundle.actual?.notice_timing || ""} disabled={readOnly || lockedSnapshot}><option value="">Select notice timing</option>{noticeTimings.map((timing) => <option key={timing}>{timing}</option>)}</select></label>
            <label>Evidence / reference<input name="evidence_ref" defaultValue={bundle.actual?.evidence_ref || ""} placeholder="Medical certificate, chat screenshot, approval note, etc." disabled={readOnly || lockedSnapshot} /></label>
            <label>Reason / notes<input name="reason" defaultValue={bundle.leave?.reason || bundle.actual?.notes || ""} disabled={readOnly || lockedSnapshot} /></label>
            {canEdit && !lockedSnapshot ? <div className="action-row"><button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : hasLeave ? "Update leave" : "Save leave / absence"}</button>{hasLeave ? <button className="button ghost" type="button" disabled={busy} onClick={clearDay}>Clear day</button> : null}</div> : null}
          </form>
        ) : null}

        {message ? <p className="footer-note">{message}</p> : null}
      </div>
    </div>
  );
}
