"use client";

import { AlertTriangle, CheckCircle2, Copy as CopyIcon, MoveRight, StickyNote, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { copyScheduledShift, moveScheduledShift } from "@/app/schedule/actions";
import { ConfirmActionModal } from "@/components/ConfirmActionModal";
import { ScheduleDayEditorModal, type ScheduleDayBundle } from "@/components/ScheduleDayEditorModal";
import { formatIsoDay } from "@/lib/period";
import type { ScheduleEmployee, ScheduleLeaveStatus, ScheduleRestDay, ScheduleShift } from "@/lib/schedule-types";
import styles from "@/app/schedule/page.module.css";
import restStyles from "./ScheduleRestDay.module.css";
import dnd from "./ScheduleDnD.module.css";

type EditorState = { day: string; shift: ScheduleShift | null; employeeId?: number | null; initialTab?: "scheduled" | "actual" | "leave" };
type ValidationIssue = { tone: "error" | "warning"; message: string };
type DropPrompt = { source: ScheduleShift; targetDay: string; targetEmployeeId: number | null; targetEmployeeName: string; issues: ValidationIssue[] };
type ClearPrompt = { employeeId: number; workDate: string };
type Props = { days: string[]; shifts: ScheduleShift[]; employees: ScheduleEmployee[]; canEdit: boolean };
type FloatingHeader = { visible: boolean; left: number; width: number; scrollLeft: number };

function numberText(value: number | null | undefined, digits = 2): string { return Number(value || 0).toLocaleString("en-PH", { minimumFractionDigits: digits, maximumFractionDigits: digits }); }
function actualText(shift: ScheduleShift) { if (shift.is_absent) return shift.absence_type || "Absent"; if (shift.actual_in || shift.actual_out) return `${shift.actual_in || "—"}–${shift.actual_out || "—"}`; return "Not recorded"; }
function actualTone(shift: ScheduleShift) { if (shift.is_absent) return styles.actualDanger; if (shift.actual_source === "legacy_schedule") return styles.actualLegacy; if (shift.actual_in || shift.actual_out) return styles.actualOk; return styles.actualMissing; }
function shiftIdentity(shift: ScheduleShift) { return [shift.employee_id || "unassigned", shift.shift_date, shift.start_time, shift.end_time, shift.position || "Other"].join("|"); }
function initials(name: string) { return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "—"; }
function dayTitle(day: string) { return new Date(`${day}T00:00:00`).toLocaleDateString("en-US", { weekday: "short", day: "numeric" }); }
function daySubtitle(day: string) { const date = new Date(`${day}T00:00:00`); const today = new Date(); const same = date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth() && date.getDate() === today.getDate(); const weekend = date.getDay() === 0 || date.getDay() === 6; if (same && weekend) return "Today · weekend"; if (same) return "Today"; return weekend ? "Weekend" : "Regular coverage"; }
function dateTime(day: string, time: string) { return new Date(`${day}T${time.length === 5 ? `${time}:00` : time}`); }
function intervalFor(shift: Pick<ScheduleShift, "shift_date" | "start_time" | "end_time">, overrideDay?: string) { const day = overrideDay || shift.shift_date; const start = dateTime(day, shift.start_time); const end = dateTime(day, shift.end_time); if (end <= start) end.setDate(end.getDate() + 1); return { start, end }; }
function overlaps(a: { start: Date; end: Date }, b: { start: Date; end: Date }) { return a.start < b.end && b.start < a.end; }

export function ScheduleBoardClient({ days, shifts, employees, canEdit }: Props) {
  const router = useRouter();
  const matrixRef = useRef<HTMLDivElement | null>(null);
  const [localShifts, setLocalShifts] = useState(shifts);
  const [dragId, setDragId] = useState<number | null>(null);
  const [selectedShiftId, setSelectedShiftId] = useState<number | null>(null);
  const [overDay, setOverDay] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [dropPrompt, setDropPrompt] = useState<DropPrompt | null>(null);
  const [clearPrompt, setClearPrompt] = useState<ClearPrompt | null>(null);
  const [restDays, setRestDays] = useState<ScheduleRestDay[]>([]);
  const [leaveStatuses, setLeaveStatuses] = useState<ScheduleLeaveStatus[]>([]);
  const [floatingHeader, setFloatingHeader] = useState<FloatingHeader>({ visible: false, left: 0, width: 0, scrollLeft: 0 });
  const [isPending, startTransition] = useTransition();

  useEffect(() => setLocalShifts(shifts), [shifts]);
  const loadDayStates = useCallback(() => { if (!days[0]) return Promise.resolve(); return Promise.all([fetch(`/api/schedule/rest-days?week_start=${encodeURIComponent(days[0])}`, { cache: "no-store" }).then((response) => response.json()), fetch(`/api/schedule/leave-statuses?week_start=${encodeURIComponent(days[0])}`, { cache: "no-store" }).then((response) => response.json())]).then(([restData, leaveData]) => { setRestDays(restData.ok ? restData.items || [] : []); setLeaveStatuses(leaveData.ok ? leaveData.items || [] : []); }).catch(() => { setRestDays([]); setLeaveStatuses([]); }); }, [days]);
  useEffect(() => { void loadDayStates(); }, [loadDayStates]);
  useEffect(() => { if (!dropPrompt) return; function closeOnEscape(event: KeyboardEvent) { if (event.key === "Escape") setDropPrompt(null); } document.addEventListener("keydown", closeOnEscape); return () => document.removeEventListener("keydown", closeOnEscape); }, [dropPrompt]);
  useEffect(() => { function openGlobalAdd() { if (days[0]) setEditor({ day: days[0], shift: null, employeeId: null, initialTab: "scheduled" }); } window.addEventListener("schedule:add-shift", openGlobalAdd); return () => window.removeEventListener("schedule:add-shift", openGlobalAdd); }, [days]);

  useEffect(() => {
    const matrix = matrixRef.current;
    const scroller = matrix?.parentElement;
    if (!matrix || !(scroller instanceof HTMLElement)) return;

    let frame = 0;
    const update = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const matrixRect = matrix.getBoundingClientRect();
        const scrollerRect = scroller.getBoundingClientRect();
        const visible = matrixRect.top < 0 && matrixRect.bottom > 58 && scrollerRect.width > 0;
        setFloatingHeader({ visible, left: scrollerRect.left, width: scrollerRect.width, scrollLeft: scroller.scrollLeft });
      });
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    scroller.addEventListener("scroll", update, { passive: true });
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      scroller.removeEventListener("scroll", update);
    };
  }, [days]);

  const visibleShifts = useMemo(() => { const plannedKeys = new Set(localShifts.filter((shift) => shift.id > 0).map(shiftIdentity)); return localShifts.filter((shift) => shift.id > 0 || !plannedKeys.has(shiftIdentity(shift))); }, [localShifts]);
  const rows = useMemo(() => { const employeeRows = employees.map((employee) => ({ id: employee.id, name: employee.full_name, code: employee.employee_code || "", department: employee.department || "", position: employee.position || "" })); const hasUnassigned = visibleShifts.some((shift) => !shift.employee_id); return hasUnassigned ? [...employeeRows, { id: null, name: "Unassigned", code: "", department: "", position: "" }] : employeeRows; }, [employees, visibleShifts]);
  const shiftsByCell = useMemo(() => visibleShifts.reduce<Record<string, ScheduleShift[]>>((acc, shift) => { const key = `${shift.employee_id || "unassigned"}:${shift.shift_date}`; acc[key] ||= []; acc[key].push(shift); return acc; }, {}), [visibleShifts]);
  const restDayKeys = useMemo(() => new Set(restDays.map((item) => `${item.employee_id}:${item.work_date}`)), [restDays]);
  const leaveByCell = useMemo(() => leaveStatuses.reduce<Record<string, ScheduleLeaveStatus>>((acc, item) => { acc[`${item.employee_id}:${item.work_date}`] = item; return acc; }, {}), [leaveStatuses]);
  function cellKey(employeeId: number | null, day: string) { return `${employeeId || "unassigned"}:${day}`; }
  function validateDestination(source: ScheduleShift, targetEmployeeId: number | null, targetDay: string): ValidationIssue[] { const issues: ValidationIssue[] = []; if (source.id <= 0 || source.movable === false || source.source === "imported") issues.push({ tone: "error", message: "Imported or legacy schedule rows cannot be moved or copied." }); if (targetEmployeeId !== null) { if (restDayKeys.has(`${targetEmployeeId}:${targetDay}`)) issues.push({ tone: "error", message: "Destination is marked as a Rest Day. Clear it first." }); const leave = leaveByCell[`${targetEmployeeId}:${targetDay}`]; if (leave) issues.push({ tone: "error", message: `Destination has ${leave.leave_type_name}. Clear the leave record first.` }); } const targetInterval = intervalFor(source, targetDay); const conflicting = visibleShifts.find((other) => other.id !== source.id && (other.employee_id || null) === targetEmployeeId && overlaps(targetInterval, intervalFor(other))); if (conflicting) issues.push({ tone: "error", message: `Overlaps ${conflicting.start_time}–${conflicting.end_time} on ${formatIsoDay(conflicting.shift_date)}.` }); if (source.shift_date === targetDay && (source.employee_id || null) === targetEmployeeId) issues.push({ tone: "error", message: "Source and destination are the same." }); if (targetEmployeeId === null) issues.push({ tone: "warning", message: "This shift will be unassigned and requires later staffing." }); return issues; }
  function openDropPrompt(source: ScheduleShift, targetEmployeeId: number | null, targetEmployeeName: string, day: string) { setMessage(""); setDropPrompt({ source, targetDay: day, targetEmployeeId, targetEmployeeName, issues: validateDestination(source, targetEmployeeId, day) }); }
  function onDrop(targetEmployeeId: number | null, targetEmployeeName: string, day: string) { if (!canEdit || !dragId) return; const source = visibleShifts.find((item) => item.id === dragId); setOverDay(null); setDragId(null); if (source) openDropPrompt(source, targetEmployeeId, targetEmployeeName, day); }
  function chooseDestination(targetEmployeeId: number | null, targetEmployeeName: string, day: string) { if (!selectedShiftId) return; const source = visibleShifts.find((item) => item.id === selectedShiftId); if (source) openDropPrompt(source, targetEmployeeId, targetEmployeeName, day); }
  function applyDrop(operation: "move" | "copy") { if (!dropPrompt || dropPrompt.issues.some((issue) => issue.tone === "error")) return; const pending = dropPrompt; const before = localShifts; const optimisticId = operation === "copy" ? -Date.now() : pending.source.id; const optimisticShift = { ...pending.source, id: optimisticId, shift_date: pending.targetDay, employee_id: pending.targetEmployeeId, employee_name: pending.targetEmployeeName, source: "planned", movable: true }; setDropPrompt(null); setSelectedShiftId(null); setLocalShifts((current) => operation === "move" ? current.map((item) => item.id === pending.source.id ? optimisticShift : item) : [...current, optimisticShift]); startTransition(async () => { const result = operation === "move" ? await moveScheduledShift(pending.source.id, pending.targetDay, pending.targetEmployeeId) : await copyScheduledShift(pending.source.id, pending.targetDay, pending.targetEmployeeId); if (!result?.ok) { setLocalShifts(before); setMessage(result?.message || `Could not ${operation} shift. Changes were rolled back.`); return; } setMessage(operation === "move" ? "Shift moved." : "Shift copied."); router.refresh(); }); }
  function setRestDay(employeeId: number, workDate: string, active: boolean) { startTransition(async () => { setMessage(""); const response = await fetch("/api/schedule/rest-days", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ employee_id: employeeId, work_date: workDate, active }) }); const data = await response.json().catch(() => ({})); if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : data.message || "Rest day was not saved."); return; } setRestDays((current) => active ? [...current.filter((item) => !(item.employee_id === employeeId && item.work_date === workDate)), data.item] : current.filter((item) => !(item.employee_id === employeeId && item.work_date === workDate))); setMessage(active ? "Rest day marked." : "Rest day cleared."); router.refresh(); }); }
  function clearDay() { if (!clearPrompt) return; const { employeeId, workDate } = clearPrompt; setClearPrompt(null); startTransition(async () => { setMessage(""); const response = await fetch("/api/schedule/day", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ section: "reset", employee_id: employeeId, work_date: workDate }) }); const data = await response.json().catch(() => ({})); if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : data.message || "Day was not cleared."); return; } setLeaveStatuses((current) => current.filter((item) => !(item.employee_id === employeeId && item.work_date === workDate))); setRestDays((current) => current.filter((item) => !(item.employee_id === employeeId && item.work_date === workDate))); setMessage("Day cleared."); router.refresh(); await loadDayStates(); }); }
  function handleEditorSaved(data: ScheduleDayBundle) { const previous = editor?.shift; setLocalShifts((current) => { if (data.shift) { const withoutSaved = current.filter((item) => item.id !== data.shift?.id && (!previous?.id || item.id !== previous.id)); return [...withoutSaved, data.shift]; } if (data.leave && previous?.id) return current.filter((item) => item.id !== previous.id); return current; }); void loadDayStates(); }

  return <>
    {(isPending || message) ? <div className={styles.boardHint}>{isPending ? "Saving…" : message}</div> : null}
    {selectedShiftId ? <div className={dnd.selectionBar}><span>Select a destination cell for the chosen shift.</span><div><button className="button small" type="button" onClick={() => setSelectedShiftId(null)}>Cancel selection</button></div></div> : null}
    <div aria-hidden={!floatingHeader.visible} className={`schedule-floating-header ${floatingHeader.visible ? "is-visible" : ""}`} style={{ left: floatingHeader.left, width: floatingHeader.width }}>
      <div className="schedule-floating-track" style={{ transform: `translateX(${-floatingHeader.scrollLeft}px)` }}>
        <div className="schedule-floating-corner">Employee</div>
        {days.map((day) => <div className="schedule-floating-day" key={day}><strong>{dayTitle(day)}</strong><span>{daySubtitle(day)}</span></div>)}
      </div>
    </div>
    <div className={`${styles.matrixGrid} ${isPending ? dnd.busy : ""}`} ref={matrixRef}>
      <div className={styles.matrixCorner}>Employee</div>
      {days.map((day) => <div className={styles.matrixHeader} key={day}><strong>{dayTitle(day)}</strong><span>{daySubtitle(day)}</span></div>)}
      {rows.map((row) => <div className={styles.matrixRow} key={row.id || "unassigned"}>
        <div className={styles.employeeCell}><span className={styles.employeeAvatar}>{initials(row.name)}</span><div><strong>{row.name}</strong><span>{[row.code, row.position || row.department].filter(Boolean).join(" · ")}</span></div></div>
        {days.map((day) => { const key = cellKey(row.id, day); const cellShifts = shiftsByCell[key] || []; const isRestDay = row.id !== null && restDayKeys.has(`${row.id}:${day}`); const leave = row.id !== null ? leaveByCell[`${row.id}:${day}`] : undefined; const isOver = overDay === `${row.id || "unassigned"}:${day}`; const selectedSource = selectedShiftId ? visibleShifts.find((item) => item.id === selectedShiftId) : null; const hasError = selectedSource ? validateDestination(selectedSource, row.id, day).some((issue) => issue.tone === "error") : false; return <div className={`${styles.scheduleCell} ${isOver ? styles.dropTarget : ""} ${isRestDay || leave ? restStyles.restDayCell : ""} ${selectedShiftId ? dnd.selectedCell : ""} ${selectedShiftId && hasError ? dnd.invalidTarget : ""}`} data-schedule-cell={`${row.id ?? "unassigned"}:${day}`} key={`${row.id || "unassigned"}-${day}`} onClick={(event) => { if (event.currentTarget !== event.target) return; if (selectedShiftId) chooseDestination(row.id, row.name, day); else if (canEdit && row.id !== null) setEditor({ day, shift: null, employeeId: row.id, initialTab: "scheduled" }); }} onDragOver={(event) => { if (!canEdit) return; event.preventDefault(); setOverDay(`${row.id || "unassigned"}:${day}`); }} onDragLeave={() => setOverDay(null)} onDrop={() => onDrop(row.id, row.name, day)}>
          <div className={styles.scheduleStack}>
            {leave ? <div className={restStyles.leaveCard}><strong>{leave.leave_type_name}</strong><span>{leave.status} · {leave.paid ? "paid" : "unpaid"}{leave.reason ? ` · ${leave.reason}` : ""}</span>{canEdit && row.id !== null ? <button className={restStyles.clearRestDay} type="button" onClick={() => setClearPrompt({ employeeId: row.id as number, workDate: day })}>Clear</button> : null}</div> : null}
            {!leave && !isRestDay && canEdit && cellShifts.length > 0 ? (
              <button
                className={styles.addShiftTop}
                type="button"
                onClick={(event) => {
                  event.stopPropagation();

                  if (selectedShiftId) {
                    chooseDestination(row.id, row.name, day);
                    return;
                  }

                  setEditor({
                    day,
                    shift: null,
                    employeeId: row.id,
                    initialTab: "scheduled",
                  });
                }}
              >
                + Add another shift
              </button>
            ) : null}
            {!leave ? cellShifts.map((shift) => { const approvedOtHours = Number(shift.approved_ot_hours || 0); const noteText = [shift.notes ? `Schedule: ${shift.notes}` : "", shift.actual_notes ? `Actual: ${shift.actual_notes}` : ""].filter(Boolean).join("\n"); return <div className={`${styles.shiftCard} ${dragId === shift.id ? styles.dragging : ""}`} draggable={canEdit && shift.id > 0 && shift.movable !== false} key={shift.id} onClick={(event) => { event.stopPropagation(); setEditor({ day, shift }); }} onDragStart={() => { if (canEdit && shift.id > 0 && shift.movable !== false) setDragId(shift.id); }} onDragEnd={() => { setDragId(null); setOverDay(null); }}>
              <span className={styles.shiftHeader}><span className={styles.shiftLabel}>Scheduled shift</span><strong className={styles.shiftTime}>{shift.start_time}–{shift.end_time}{shift.is_overnight ? " +1" : ""}</strong></span>
              <span className={styles.shiftPosition}>{shift.position || "Other"}</span>
              <div className={styles.shiftMeta}><span>{numberText(shift.planned_paid_hours)}h</span><span>{shift.break_minutes}m break</span></div>
              <div className={`${styles.actualLine} ${actualTone(shift)}`}><strong className={styles.actualValue}>{actualText(shift)}</strong></div>
              <div className={styles.shiftFlags}>{shift.actual_status ? <span className={styles.actualStatus}>{shift.actual_status}</span> : null}{approvedOtHours > 0 ? <span className={styles.otFlag}>OT {numberText(approvedOtHours)}h</span> : null}{shift.actual_source === "legacy_schedule" ? <span className={styles.legacyNote}>Legacy actual</span> : null}{shift.source === "imported" ? <span className={styles.legacyNote}>Imported shift</span> : null}</div>
              {noteText ? <span aria-label={noteText} className={styles.noteFlag} title={noteText}><StickyNote aria-hidden="true" size={13} />Note</span> : null}
            </div>; }) : null}
            {!leave && cellShifts.length === 0 && isRestDay ? <div className={restStyles.restDayCard}><strong>Rest Day</strong><span>Weekly rest day</span>{canEdit && row.id !== null ? <button className={restStyles.clearRestDay} type="button" onClick={() => setRestDay(row.id as number, day, false)}>Clear</button> : null}</div> : null}
            {!leave && !isRestDay && canEdit && cellShifts.length === 0 ? <button className={styles.emptyDay} type="button" onClick={() => selectedShiftId ? chooseDestination(row.id, row.name, day) : setEditor({ day, shift: null, employeeId: row.id, initialTab: "scheduled" })}>{selectedShiftId ? "Use destination" : "+ Add shift"}</button> : null}
          </div>
        </div>; })}
      </div>)}
    </div>
    <ConfirmActionModal
      open={Boolean(clearPrompt)}
      title="Clear this schedule day?"
      description="This clears the current day state so you can choose Add shift, Rest day, or Leave again."
      confirmLabel="Clear day"
      danger
      busy={isPending}
      onClose={() => setClearPrompt(null)}
      onConfirm={clearDay}
    />
    {dropPrompt ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) setDropPrompt(null); }} role="presentation"><section aria-labelledby="schedule-drop-title" aria-modal="true" className="modal-panel compact-modal" role="dialog"><div className="panel-title"><div><span className="eyebrow">Schedule validation</span><h2 id="schedule-drop-title">Move or copy shift?</h2></div><button aria-label="Close" className="button ghost small" onClick={() => setDropPrompt(null)} type="button"><X aria-hidden="true" size={16} /></button></div><div className={styles.dropSummary}><div className={styles.dropEndpoint}><span>From</span><strong>{dropPrompt.source.employee_name || "Unassigned"} · {formatIsoDay(dropPrompt.source.shift_date)}</strong><small>{dropPrompt.source.start_time}–{dropPrompt.source.end_time} · {dropPrompt.source.position || "Other"}</small></div><MoveRight aria-hidden="true" className={styles.dropArrow} size={20} /><div className={styles.dropEndpoint}><span>To</span><strong>{dropPrompt.targetEmployeeName} · {formatIsoDay(dropPrompt.targetDay)}</strong><small>{dropPrompt.source.start_time}–{dropPrompt.source.end_time} · {dropPrompt.source.position || "Other"}</small></div></div><div className={dnd.validationList}>{dropPrompt.issues.length ? dropPrompt.issues.map((issue, index) => <div className={`${dnd.validationItem} ${issue.tone === "error" ? dnd.validationError : dnd.validationWarning}`} key={`${issue.message}-${index}`}><AlertTriangle size={16} /><span>{issue.message}</span></div>) : <div className={dnd.validationItem}><CheckCircle2 size={16} /><span>Destination passed overlap, leave, and rest-day checks.</span></div>}</div><div className={`action-row ${styles.dropActions}`}><button autoFocus className="button" disabled={isPending || dropPrompt.issues.some((issue) => issue.tone === "error")} onClick={() => applyDrop("move")} type="button"><MoveRight aria-hidden="true" size={16} />Move</button><button className="button ghost" disabled={isPending || dropPrompt.issues.some((issue) => issue.tone === "error")} onClick={() => applyDrop("copy")} type="button"><CopyIcon aria-hidden="true" size={16} />Copy</button><button className="button ghost" disabled={isPending} onClick={() => setDropPrompt(null)} type="button">Cancel</button></div></section></div> : null}
    <ScheduleDayEditorModal key={editor ? `${editor.day}:${editor.shift?.id ?? "new"}:${editor.employeeId ?? "none"}` : "closed"} open={Boolean(editor)} day={editor?.day || days[0]} shift={editor?.shift || null} initialEmployeeId={editor?.employeeId || null} initialTab={editor?.initialTab || "scheduled"} employees={employees} canEdit={canEdit} onSaved={handleEditorSaved} onClose={() => { setEditor(null); void loadDayStates(); }} />
  </>;
}
