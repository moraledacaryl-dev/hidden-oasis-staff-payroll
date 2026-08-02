"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AppDrawer, AppModal, SurfaceContext, SurfaceSection } from "@/components/AppSurface";
import type { ScheduleEmployee, ScheduleShift } from "@/lib/schedule-types";

const positions = ["Receptionist", "Cook", "Barista", "Bartender", "Security", "Housekeeper", "Other"];
const leaveKinds = ["None", "SIL", "Sick Leave", "Vacation Leave", "Emergency Leave", "Bereavement Leave", "Official Business", "Other Approved Absence", "Approved / Excused Absence", "Unexcused Absence", "AWOL"];
const noticeTimings = ["In advance", "At least 1 hour before shift", "After shift start", "No notice"];
const attendanceStatuses = ["Needs Review", "Approved"];

type TabKey = "scheduled" | "actual" | "leave" | "rest";
export type ScheduleDayBundle = {
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
  initialTab?: "scheduled" | "actual" | "leave";
  employees: ScheduleEmployee[];
  canEdit: boolean;
  onClose: () => void;
  onSaved?: (bundle: ScheduleDayBundle) => void;
};

function emptyBundle(): ScheduleDayBundle { return { ok: true, shift: null, actual: null, leave: null }; }
function formatDate(day: string) { return new Date(`${day}T00:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric", year: "numeric" }); }

export function ScheduleDayEditorModal({ open, day, shift, initialEmployeeId = null, initialTab = "scheduled", employees, canEdit, onClose, onSaved }: Props) {
  const router = useRouter();
  const [tab, setTab] = useState<TabKey>(initialTab);
  const [bundle, setBundle] = useState<ScheduleDayBundle>(emptyBundle());
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [clearReason, setClearReason] = useState("");
  const [clearConfirm, setClearConfirm] = useState("");
  const formRef = useRef<HTMLFormElement | null>(null);
  const busyRef = useRef(false);
  const initialEmployeeIdValue = shift?.employee_id ? String(shift.employee_id) : (initialEmployeeId ? String(initialEmployeeId) : "");
  const [employeeId, setEmployeeId] = useState(initialEmployeeIdValue);
  const [shiftDate, setShiftDate] = useState(day);

  useEffect(() => {
    if (!open) return;

    const controller = new AbortController();
    const selectedDay = shift?.shift_date || day;
    const selectedEmployeeId = shift?.employee_id || initialEmployeeId;

    busyRef.current = false;
    setBusy(false);
    setLoading(true);
    setBundle(emptyBundle());
    setTab(initialTab);
    setMessage("");
    setClearOpen(false);
    setClearReason("");
    setClearConfirm("");
    setEmployeeId(selectedEmployeeId ? String(selectedEmployeeId) : "");
    setShiftDate(selectedDay);

    const params = new URLSearchParams();
    params.set("shift_date", selectedDay);
    if (shift?.id) params.set("shift_id", String(shift.id));
    else if (selectedEmployeeId) params.set("employee_id", String(selectedEmployeeId));

    if (!shift?.id && !selectedEmployeeId) {
      setLoading(false);
      return () => controller.abort();
    }

    fetch(`/api/schedule/day?${params.toString()}`, { cache: "no-store", signal: controller.signal })
      .then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.message || "Could not load employee-day details.");
        return data as ScheduleDayBundle;
      })
      .then((data) => {
        if (controller.signal.aborted) return;
        setBundle(data);
        if (data.leave) setTab("leave");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setMessage(error instanceof Error ? error.message : "Could not load employee-day details.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [day, initialEmployeeId, initialTab, open, shift]);

  // Preserve the user's intent. When "+ Add another shift" opens the
  // drawer, `shift` is null. The employee-day lookup may still return an
  // existing shift in `bundle.shift`, but that existing shift must not turn
  // this create operation into an edit operation.
  const creatingNewShift = !shift?.id;
  const currentShift = creatingNewShift
    ? null
    : (bundle.shift || shift);

  const selectedEmployee = useMemo(
    () => employees.find(
      (item) => String(item.id) === employeeId,
    ),
    [employeeId, employees],
  );

  const readOnly = (
    !canEdit
    || (
      !creatingNewShift
      && Boolean(bundle.legacy_read_only)
    )
  );
  const lockedSnapshot = Boolean(bundle.payroll_locked);
  const hasLeave = Boolean(bundle.leave);

  function beginBusy(): boolean {
    if (busyRef.current || loading) return false;
    busyRef.current = true;
    setBusy(true);
    setMessage("");
    return true;
  }

  function endBusy() {
    busyRef.current = false;
    setBusy(false);
  }

  async function save(section: "scheduled" | "actual" | "leave", payload: Record<string, unknown>) {
    if (hasLeave && section !== "leave") { setMessage("Clear the day first before adding a shift or actual attendance."); setTab("leave"); return; }
    if (!beginBusy()) return;

    try {
      const response = await fetch("/api/schedule/day", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ section, ...payload }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : data.message || "Not saved."); return; }
      const saved = data as ScheduleDayBundle;
      setBundle(saved);
      onSaved?.(saved);
      router.refresh();
      onClose();
    } catch {
      setMessage("The employee day could not be saved. Please try again.");
    } finally {
      endBusy();
    }
  }

  async function saveRestDay() {
    if (!employeeId) { setMessage("Choose an employee before marking a Rest Day."); return; }
    if (!beginBusy()) return;
    try {
      const response = await fetch("/api/schedule/rest-days", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ employee_id: Number(employeeId), work_date: shiftDate, active: true }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : data.message || "Rest day was not saved."); return; }
      router.refresh();
      onClose();
    } catch {
      setMessage("The rest day could not be saved. Please try again.");
    } finally {
      endBusy();
    }
  }

  async function clearDay() {
    if (!employeeId) return;
    if (clearReason.trim().length < 10) { setMessage("Enter a Clear Day reason with at least 10 characters."); return; }
    if (clearConfirm.trim() !== "CLEAR DAY") { setMessage("Type CLEAR DAY to confirm."); return; }
    if (!beginBusy()) return;
    try {
      const response = await fetch("/api/schedule/day", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ section: "reset", employee_id: Number(employeeId), work_date: shiftDate, clear_reason: clearReason.trim(), confirmation: clearConfirm.trim() }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : data.message || "Day was not cleared."); return; }
      setBundle(emptyBundle());
      setClearOpen(false);
      router.refresh();
      onClose();
    } catch {
      setMessage("The employee day could not be cleared. Please try again.");
    } finally {
      endBusy();
    }
  }

  async function deleteShift() {
    if (!currentShift?.id || !beginBusy()) return;
    try {
      const response = await fetch("/api/schedule/day", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ section: "remove", shift_id: currentShift.id }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : data.message || "Shift was not deleted."); return; }
      router.refresh();
      onClose();
    } catch {
      setMessage("The shift could not be deleted. Please try again.");
    } finally {
      endBusy();
    }
  }

  function submitActiveForm() {
    if (busyRef.current || busy || loading) return;
    formRef.current?.requestSubmit();
  }

  function saveScheduled(formData: FormData) { void save("scheduled", { shift_id: currentShift?.id || null, employee_id: Number(formData.get("employee_id") || 0) || null, shift_date: String(formData.get("shift_date") || shiftDate), start_time: String(formData.get("start_time") || "08:00"), end_time: String(formData.get("end_time") || "17:00"), position: String(formData.get("position") || "Other"), department: String(formData.get("department") || "") || null, break_minutes: Number(formData.get("break_minutes") || 0), notes: String(formData.get("notes") || "") || null }); }
  function saveActual(formData: FormData) { if (!employeeId) { setMessage("Choose an employee before saving actual attendance."); return; } void save("actual", { employee_id: Number(employeeId), shift_date: shiftDate, actual_in: String(formData.get("actual_in") || "") || null, actual_out: String(formData.get("actual_out") || "") || null, attendance_status: String(formData.get("attendance_status") || "Needs Review"), actual_exception_status: String(formData.get("actual_exception_status") || "") || null, evidence_ref: String(formData.get("evidence_ref") || "") || null, approved_ot_hours: Number(formData.get("approved_ot_hours") || 0), notes: String(formData.get("notes") || "") || null }); }
  function saveLeave(formData: FormData) { if (!employeeId) { setMessage("Choose an employee before saving leave or absence."); return; } const rawHours = String(formData.get("leave_hours") || "").trim(); void save("leave", { employee_id: Number(employeeId), shift_date: shiftDate, leave_kind: String(formData.get("leave_kind") || "None"), leave_days: rawHours ? null : Number(formData.get("leave_days") || 1), leave_hours: rawHours ? Number(rawHours) : null, reason: String(formData.get("reason") || "") || null, notice_given_at: String(formData.get("notice_given_at") || "") || null, notice_timing: String(formData.get("notice_timing") || "") || null, evidence_ref: String(formData.get("evidence_ref") || "") || null }); }

  const actualAbsenceType = String(bundle.actual?.absence_type || "").toLowerCase();
  const actualExceptionDefault = actualAbsenceType.includes("unexcused") ? "Unexcused" : actualAbsenceType.includes("excused") ? "Excused" : "";
  const title = selectedEmployee?.full_name || currentShift?.employee_name || (currentShift ? "Schedule day" : "Add shift");
  const description = currentShift ? `${formatDate(shiftDate)} · Edit the planned day and actual attendance without changing saved payroll snapshots.` : "Choose a person and date, then define the planned day state.";

  const footer = (
    <>
      <div className="app-surface-footer-left">
        {canEdit && currentShift?.id ? <button className="button danger" disabled={busy || loading} onClick={() => setClearOpen(true)} type="button">Delete / clear</button> : null}
      </div>
      <div className="app-surface-footer-right">
        <button className="button ghost" disabled={busy} onClick={onClose} type="button">Cancel</button>
        {canEdit && tab === "rest" ? <button className="button" disabled={busy || loading || lockedSnapshot} onClick={saveRestDay} type="button">{busy ? "Saving…" : "Save Rest Day"}</button> : null}
        {canEdit && tab !== "rest" ? <button className="button" disabled={busy || loading || (lockedSnapshot && tab === "leave")} onClick={submitActiveForm} type="button">{loading ? "Loading…" : busy ? "Saving…" : tab === "actual" ? "Save actual" : tab === "leave" ? (hasLeave ? "Update leave" : "Save leave") : (currentShift ? "Save changes" : "Add shift")}</button> : null}
      </div>
    </>
  );

  return (
    <>
      <AppDrawer open={open} eyebrow="Employee day" title={title} description={description} footer={footer} onClose={onClose}>
        <SurfaceContext>
          <div><span>Employee</span><strong>{selectedEmployee?.full_name || currentShift?.employee_name || "Not selected"}</strong></div>
          <div><span>Employee code</span><strong>{selectedEmployee?.employee_code || "—"}</strong></div>
          <div><span>Date</span><strong>{formatDate(shiftDate)}</strong></div>
        </SurfaceContext>

        {loading ? <div className="app-surface-notice info" role="status"><strong>Loading this employee day…</strong><span>The drawer will update with the selected cell before editing is enabled.</span></div> : null}
        {lockedSnapshot ? <div className="app-surface-notice warning"><strong>Saved payroll snapshot</strong><span>Payroll run #{bundle.paid_run?.id} remains unchanged until a revised run is saved.</span></div> : null}
        {bundle.legacy_read_only ? <div className="app-surface-notice"><strong>Legacy read-only record</strong><span>This historical row is retained for audit and cannot be changed.</span></div> : null}
        {hasLeave ? <div className="app-surface-notice info"><strong>Leave is active for this day</strong><span>Clear the day before switching back to a shift or actual attendance.</span></div> : null}
        {bundle.message ? <div className="app-surface-notice"><span>{bundle.message}</span></div> : null}

        <SurfaceSection number="1" title="Planned day state" description="Choose the schedule state staff should see.">
          <div className="app-segmented-control">
            {!hasLeave ? <button className={tab === "scheduled" ? "active" : ""} disabled={loading} onClick={() => setTab("scheduled")} type="button">Shift</button> : null}
            {!hasLeave ? <button className={tab === "rest" ? "active" : ""} disabled={loading} onClick={() => setTab("rest")} type="button">Rest Day</button> : null}
            <button className={tab === "leave" ? "active" : ""} disabled={loading} onClick={() => setTab("leave")} type="button">Leave</button>
          </div>

          {!hasLeave && tab === "scheduled" ? <form action={saveScheduled} className="app-surface-form" ref={formRef}>
            <label>Date<input name="shift_date" type="date" value={shiftDate} disabled={readOnly || loading} onChange={(event) => setShiftDate(event.target.value)} required /></label>
            <label>Person<select name="employee_id" value={employeeId} disabled={readOnly || loading} onChange={(event) => setEmployeeId(event.target.value)} required><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
            <label>Start<input name="start_time" type="time" defaultValue={currentShift?.start_time || "08:00"} disabled={readOnly || loading} required /></label>
            <label>End<input name="end_time" type="time" defaultValue={currentShift?.end_time || "17:00"} disabled={readOnly || loading} required /></label>
            <label>Role<select name="position" defaultValue={currentShift?.position || selectedEmployee?.position || "Other"} disabled={readOnly || loading}>{positions.map((p) => <option key={p} value={p}>{p}</option>)}</select></label>
            <label>Department<input name="department" defaultValue={currentShift?.employee_department || currentShift?.department || selectedEmployee?.department || ""} disabled={readOnly || loading} /></label>
            <label>Break minutes<input name="break_minutes" type="number" min="0" defaultValue={currentShift?.break_minutes ?? 60} disabled={readOnly || loading} /></label>
            <label className="full">Schedule note<textarea name="notes" rows={3} defaultValue={currentShift?.notes || ""} disabled={readOnly || loading} /></label>
          </form> : null}

          {!hasLeave && tab === "rest" ? <div className="app-state-preview"><strong>Rest Day</strong><p>No scheduled shift will be shown for this employee and date. Actual attendance remains separate.</p><label>Employee<select value={employeeId} disabled={readOnly || loading} onChange={(event) => setEmployeeId(event.target.value)}><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label><label>Date<input type="date" value={shiftDate} disabled={readOnly || loading} onChange={(event) => setShiftDate(event.target.value)} /></label></div> : null}

          {tab === "leave" ? <form action={saveLeave} className="app-surface-form" ref={formRef}>
            <label>Employee<select value={employeeId} disabled={readOnly || loading || lockedSnapshot || hasLeave} onChange={(event) => setEmployeeId(event.target.value)}><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
            <label>Leave type<select name="leave_kind" defaultValue={bundle.leave?.leave_type_name || bundle.actual?.absence_type || "None"} disabled={readOnly || loading || lockedSnapshot}>{leaveKinds.map((kind) => <option key={kind}>{kind}</option>)}</select></label>
            <label>Days<input name="leave_days" type="number" min="0.25" step="0.25" defaultValue={bundle.leave?.days ?? 1} disabled={readOnly || loading || lockedSnapshot} /></label>
            <label>Hours, if partial<input name="leave_hours" type="number" min="0" step="0.25" defaultValue={bundle.leave?.paid_hours ?? ""} disabled={readOnly || loading || lockedSnapshot} /></label>
            <label>Date informed<input name="notice_given_at" type="datetime-local" defaultValue={bundle.actual?.notice_given_at ? String(bundle.actual.notice_given_at).replace(" ", "T").slice(0, 16) : ""} disabled={readOnly || loading || lockedSnapshot} /></label>
            <label>Notice timing<select name="notice_timing" defaultValue={bundle.actual?.notice_timing || ""} disabled={readOnly || loading || lockedSnapshot}><option value="">Select notice timing</option>{noticeTimings.map((timing) => <option key={timing}>{timing}</option>)}</select></label>
            <label className="full">Evidence or reference<input name="evidence_ref" defaultValue={bundle.actual?.evidence_ref || ""} placeholder="Medical certificate, approval note, chat screenshot, etc." disabled={readOnly || loading || lockedSnapshot} /></label>
            <label className="full">Reason and notes<textarea name="reason" rows={3} defaultValue={bundle.leave?.reason || bundle.actual?.notes || ""} disabled={readOnly || loading || lockedSnapshot} /></label>
          </form> : null}
        </SurfaceSection>

        {!hasLeave && currentShift ? <SurfaceSection number="2" title="Actual attendance" description="Operational corrections remain separate from the published schedule.">
          <div className="app-segmented-control compact"><button className={tab === "actual" ? "active" : ""} disabled={loading} onClick={() => setTab("actual")} type="button">Edit actual attendance</button></div>
          {tab === "actual" ? <form action={saveActual} className="app-surface-form" ref={formRef}>
            <label>Actual in<input name="actual_in" type="time" defaultValue={bundle.actual?.actual_in || ""} disabled={readOnly || loading} /></label>
            <label>Actual out<input name="actual_out" type="time" defaultValue={bundle.actual?.actual_out || ""} disabled={readOnly || loading} /></label>
            <label>Status<select name="attendance_status" defaultValue={bundle.actual?.attendance_status || "Needs Review"} disabled={readOnly || loading}>{attendanceStatuses.map((status) => <option key={status}>{status}</option>)}</select></label>
            <label>Exception classification<select name="actual_exception_status" defaultValue={actualExceptionDefault} disabled={readOnly || loading}><option value="">None / not applicable</option><option value="Excused">Excused</option><option value="Unexcused">Unexcused</option></select></label>
            <label>Approved OT<input name="approved_ot_hours" type="number" min="0" step="0.25" defaultValue={bundle.actual?.approved_ot_hours ?? 0} disabled={readOnly || loading} /></label>
            <label>Evidence / photo reference<input name="evidence_ref" defaultValue={bundle.actual?.evidence_ref || ""} disabled={readOnly || loading} /></label>
            <label className="full">Admin note<textarea name="notes" rows={3} defaultValue={bundle.actual?.notes || ""} disabled={readOnly || loading} /></label>
          </form> : <div className="app-state-preview"><strong>{bundle.actual?.actual_in || bundle.actual?.actual_out ? `${bundle.actual?.actual_in || "—"}–${bundle.actual?.actual_out || "—"}` : "No actual attendance recorded"}</strong><p>{bundle.actual?.attendance_status || "Actual attendance can be added or corrected here."}</p></div>}
        </SurfaceSection> : null}

        {message ? <div className="app-surface-notice" role="status"><span>{message}</span></div> : null}
      </AppDrawer>

      <AppModal open={clearOpen} eyebrow="Destructive action" title={currentShift?.id ? "Delete or clear employee day?" : "Clear employee day?"} description="Saved payroll runs remain unchanged unless a revised run is saved." onClose={() => setClearOpen(false)} footer={<><button className="button ghost" onClick={() => setClearOpen(false)} type="button">Cancel</button><div className="app-surface-footer-right">{currentShift?.id ? <button className="button danger" disabled={busy} onClick={deleteShift} type="button">Delete shift only</button> : null}<button className="button danger" disabled={busy || clearReason.trim().length < 10 || clearConfirm.trim() !== "CLEAR DAY"} onClick={clearDay} type="button">Clear entire day</button></div></>}>
        <div className="app-surface-notice warning"><strong>This removes operational records for this employee and date.</strong><span>Shift, actual attendance, leave/absence, and rest-day markers may be cleared.</span></div>
        <div className="app-surface-form single-column"><label>Reason<textarea rows={3} value={clearReason} onChange={(event) => setClearReason(event.target.value)} placeholder="Explain why this employee day must be cleared" /></label><label>Type CLEAR DAY<input value={clearConfirm} onChange={(event) => setClearConfirm(event.target.value)} placeholder="CLEAR DAY" /></label></div>
      </AppModal>
    </>
  );
}
