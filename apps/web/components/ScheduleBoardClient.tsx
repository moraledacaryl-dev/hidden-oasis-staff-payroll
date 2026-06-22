"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { moveScheduledShift } from "@/app/schedule/actions";
import { ScheduleDayEditorModal } from "@/components/ScheduleDayEditorModal";
import styles from "@/app/schedule/page.module.css";
import restStyles from "./ScheduleRestDay.module.css";

type Shift = {
  id: number;
  employee_id: number | null;
  shift_date: string;
  start_time: string;
  end_time: string;
  position: string;
  department?: string | null;
  employee_department?: string | null;
  break_minutes: number;
  status: string;
  notes?: string | null;
  employee_name?: string | null;
  planned_paid_hours: number;
  is_overnight: boolean;
  source?: string;
  movable?: boolean;
  actual_in?: string | null;
  actual_out?: string | null;
  actual_status?: string | null;
  actual_source?: string | null;
  actual_notes?: string | null;
  is_absent?: number | null;
  absence_type?: string | null;
  approved_ot_hours?: number | null;
};

type RestDay = { id: number; employee_id: number; work_date: string; notes?: string | null };
type LeaveStatus = { id: number; employee_id: number; work_date: string; leave_type_name: string; paid: number; status: string; reason?: string | null };
type ScheduleEmployee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };
type EditorState = { day: string; shift: Shift | null; employeeId?: number | null; initialTab?: "scheduled" | "actual" | "leave" };

type Props = {
  days: string[];
  shifts: Shift[];
  employees: ScheduleEmployee[];
  canEdit: boolean;
};

function numberText(value: number | null | undefined, digits = 2): string {
  return Number(value || 0).toLocaleString("en-PH", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function dayLabel(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-PH", { weekday: "short", month: "short", day: "numeric" });
}

function actualText(shift: Shift) {
  if (shift.is_absent) return shift.absence_type || "Absent";
  if (shift.actual_in || shift.actual_out) return `${shift.actual_in || "—"}–${shift.actual_out || "—"}`;
  return "Not recorded";
}

function actualTone(shift: Shift) {
  if (shift.is_absent) return styles.actualDanger;
  if (shift.actual_source === "legacy_schedule") return styles.actualLegacy;
  if (shift.actual_in || shift.actual_out) return styles.actualOk;
  return styles.actualMissing;
}

function shiftIdentity(shift: Shift) {
  return [shift.employee_id || "unassigned", shift.shift_date, shift.start_time, shift.end_time, shift.position || "Other"].join("|");
}

export function ScheduleBoardClient({ days, shifts, employees, canEdit }: Props) {
  const router = useRouter();
  const [dragId, setDragId] = useState<number | null>(null);
  const [overDay, setOverDay] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [restDays, setRestDays] = useState<RestDay[]>([]);
  const [leaveStatuses, setLeaveStatuses] = useState<LeaveStatus[]>([]);
  const [isPending, startTransition] = useTransition();

  const loadDayStates = useCallback(() => {
    if (!days[0]) return Promise.resolve();
    return Promise.all([
      fetch(`/api/schedule/rest-days?week_start=${encodeURIComponent(days[0])}`, { cache: "no-store" }).then((response) => response.json()),
      fetch(`/api/schedule/leave-statuses?week_start=${encodeURIComponent(days[0])}`, { cache: "no-store" }).then((response) => response.json()),
    ]).then(([restData, leaveData]) => {
      setRestDays(restData.ok ? restData.items || [] : []);
      setLeaveStatuses(leaveData.ok ? leaveData.items || [] : []);
    }).catch(() => {
      setRestDays([]);
      setLeaveStatuses([]);
    });
  }, [days]);

  useEffect(() => {
    void loadDayStates();
  }, [loadDayStates]);

  const visibleShifts = useMemo(() => {
    const plannedKeys = new Set(shifts.filter((shift) => shift.id > 0).map(shiftIdentity));
    return shifts.filter((shift) => shift.id > 0 || !plannedKeys.has(shiftIdentity(shift)));
  }, [shifts]);

  const rows = useMemo(() => {
    const employeeRows = employees.map((employee) => ({ id: employee.id, name: employee.full_name, department: employee.department || "", position: employee.position || "" }));
    const hasUnassigned = visibleShifts.some((shift) => !shift.employee_id);
    return hasUnassigned ? [...employeeRows, { id: null, name: "Unassigned", department: "", position: "" }] : employeeRows;
  }, [employees, visibleShifts]);

  const shiftsByCell = useMemo(() => visibleShifts.reduce<Record<string, Shift[]>>((acc, shift) => {
    const key = `${shift.employee_id || "unassigned"}:${shift.shift_date}`;
    acc[key] ||= [];
    acc[key].push(shift);
    return acc;
  }, {}), [visibleShifts]);

  const restDayKeys = useMemo(() => new Set(restDays.map((item) => `${item.employee_id}:${item.work_date}`)), [restDays]);
  const leaveByCell = useMemo(() => leaveStatuses.reduce<Record<string, LeaveStatus>>((acc, item) => {
    acc[`${item.employee_id}:${item.work_date}`] = item;
    return acc;
  }, {}), [leaveStatuses]);

  function cellKey(employeeId: number | null, day: string) {
    return `${employeeId || "unassigned"}:${day}`;
  }

  function onDrop(day: string) {
    if (!canEdit || !dragId) return;
    const source = visibleShifts.find((item) => item.id === dragId);
    setOverDay(null);
    setDragId(null);
    if (!source || source.shift_date === day) return;
    startTransition(async () => {
      const result = await moveScheduledShift(source.id, day);
      if (!result?.ok) { setMessage(result?.message || "Could not move shift."); return; }
      setMessage("Shift moved.");
      router.refresh();
    });
  }

  function setRestDay(employeeId: number, workDate: string, active: boolean) {
    startTransition(async () => {
      setMessage("");
      const response = await fetch("/api/schedule/rest-days", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employee_id: employeeId, work_date: workDate, active }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : data.message || "Rest day was not saved."); return; }
      setRestDays((current) => active
        ? [...current.filter((item) => !(item.employee_id === employeeId && item.work_date === workDate)), data.item]
        : current.filter((item) => !(item.employee_id === employeeId && item.work_date === workDate)));
      setMessage(active ? "Rest day marked." : "Rest day cleared.");
      router.refresh();
    });
  }

  function clearDay(employeeId: number, workDate: string) {
    if (!window.confirm("Clear this entire day and choose Add shift, Rest day, or Leave again?")) return;
    startTransition(async () => {
      setMessage("");
      const response = await fetch("/api/schedule/day", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ section: "reset", employee_id: employeeId, work_date: workDate }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setMessage(typeof data.detail === "string" ? data.detail : data.message || "Day was not cleared.");
        return;
      }
      setLeaveStatuses((current) => current.filter((item) => !(item.employee_id === employeeId && item.work_date === workDate)));
      setRestDays((current) => current.filter((item) => !(item.employee_id === employeeId && item.work_date === workDate)));
      setMessage("Day cleared.");
      router.refresh();
      await loadDayStates();
    });
  }

  return (
    <>
      {(isPending || message) ? <div className={styles.boardHint}>{isPending ? "Saving…" : message}</div> : null}
      <div className={styles.matrixGrid}>
        <div className={styles.matrixCorner}>Staff</div>
        {days.map((day) => <div className={styles.matrixHeader} key={day}>{dayLabel(day)}</div>)}
        {rows.map((row) => (
          <div className={styles.matrixRow} key={row.id || "unassigned"}>
            <div className={styles.employeeCell}>
              <strong>{row.name}</strong>
              {row.department || row.position ? <span>{[row.department, row.position].filter(Boolean).join(" · ")}</span> : null}
            </div>
            {days.map((day) => {
              const key = cellKey(row.id, day);
              const cellShifts = shiftsByCell[key] || [];
              const isRestDay = row.id !== null && restDayKeys.has(`${row.id}:${day}`);
              const leave = row.id !== null ? leaveByCell[`${row.id}:${day}`] : undefined;
              const isUnavailable = isRestDay || Boolean(leave);
              const isOver = overDay === `${row.id || "unassigned"}:${day}`;
              return (
                <div
                  className={`${styles.scheduleCell} ${isOver ? styles.dropTarget : ""} ${isUnavailable ? restStyles.restDayCell : ""}`}
                  key={`${row.id || "unassigned"}-${day}`}
                  onDragOver={(event) => {
                    if (!canEdit || isUnavailable) return;
                    event.preventDefault();
                    setOverDay(`${row.id || "unassigned"}:${day}`);
                  }}
                  onDragLeave={() => setOverDay(null)}
                  onDrop={() => !isUnavailable && onDrop(day)}
                >
                  <div className={styles.scheduleStack}>
                    {leave ? (
                      <div className={restStyles.leaveCard}>
                        <strong>{leave.leave_type_name}</strong>
                        {canEdit && row.id !== null ? <button className={restStyles.clearRestDay} type="button" onClick={() => clearDay(row.id as number, day)}>Clear</button> : null}
                      </div>
                    ) : null}

                    {!leave ? cellShifts.map((shift) => (
                      <button
                        type="button"
                        className={`${styles.shiftCard} ${dragId === shift.id ? styles.dragging : ""}`}
                        draggable={canEdit && shift.id > 0 && shift.movable !== false}
                        key={shift.id}
                        onClick={() => setEditor({ day, shift })}
                        onDragStart={() => { if (canEdit && shift.id > 0 && shift.movable !== false) setDragId(shift.id); }}
                        onDragEnd={() => { setDragId(null); setOverDay(null); }}
                      >
                        <div className={styles.shiftTop}><strong>Sched {shift.start_time}–{shift.end_time}{shift.is_overnight ? " +1" : ""}</strong><span>{shift.position}</span></div>
                        <span>{numberText(shift.planned_paid_hours)} hrs scheduled · break {shift.break_minutes}m</span>
                        <div className={`${styles.actualLine} ${actualTone(shift)}`}><strong>Actual</strong><span>{actualText(shift)}</span></div>
                        {shift.actual_status ? <span className={styles.actualStatus}>{shift.actual_status}{shift.actual_source === "legacy_schedule" ? " · legacy" : ""}</span> : null}
                        {shift.source === "imported" ? <span className={styles.legacyNote}>Legacy imported row</span> : null}
                        {shift.notes ? <p className="muted">{shift.notes}</p> : null}
                      </button>
                    )) : null}

                    {!leave && cellShifts.length === 0 && isRestDay ? (
                      <div className={restStyles.restDayCard}>
                        <strong>Rest Day</strong>
                        {canEdit && row.id !== null ? <button className={restStyles.clearRestDay} type="button" onClick={() => setRestDay(row.id as number, day, false)}>Clear</button> : null}
                      </div>
                    ) : null}

                    {!leave && cellShifts.length === 0 && !isRestDay ? (
                      <div className={restStyles.emptyDayActions}>
                        <button className={styles.emptyDay} type="button" onClick={() => canEdit && setEditor({ day, shift: null, employeeId: row.id, initialTab: "scheduled" })}>{canEdit ? "Add shift" : "—"}</button>
                        {canEdit && row.id !== null ? <button className={restStyles.markRestDay} type="button" onClick={() => setRestDay(row.id as number, day, true)}>Rest day</button> : null}
                        {canEdit && row.id !== null ? <button className={restStyles.markLeave} type="button" onClick={() => setEditor({ day, shift: null, employeeId: row.id, initialTab: "leave" })}>Leave</button> : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <ScheduleDayEditorModal
        open={Boolean(editor)}
        day={editor?.day || days[0]}
        shift={editor?.shift || null}
        initialEmployeeId={editor?.employeeId || null}
        initialTab={editor?.initialTab || "scheduled"}
        employees={employees}
        canEdit={canEdit}
        onClose={() => {
          setEditor(null);
          void loadDayStates();
        }}
      />
    </>
  );
}
