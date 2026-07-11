import Link from "next/link";
import { redirect } from "next/navigation";
import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { currentSession } from "@/lib/session";
import { numberText } from "@/lib/api";
import { ScheduleShiftForm } from "@/components/ScheduleShiftForm";
import { ScheduleCopyWeekForm } from "@/components/ScheduleCopyWeekForm";
import { ScheduleBoardClient } from "@/components/ScheduleBoardClient";
import { ScheduleRiskPanel } from "@/components/ScheduleRiskPanel";
import { SchedulePublishControl } from "@/components/SchedulePublishControl";
import { apiBaseUrl as baseUrl, backendHeaders } from "@/lib/backend";
import { addIsoDays, formatIsoDay, mondayOfWeek } from "@/lib/period";
import type { ScheduleActual, ScheduleEmployee, ScheduleShift } from "@/lib/schedule-types";
import styles from "./page.module.css";
import pass2 from "./pass2.module.css";

type WeekResponse = { ok: boolean; week_start: string; week_end: string; items: ScheduleShift[]; mode: string };
type ActualsResponse = { ok: boolean; week_start: string; week_end: string; items: ScheduleActual[]; mode: string };
function addWeek(iso: string, weeks: number) { return addIsoDays(iso, weeks * 7); }
function uniq(values: string[]) { return Array.from(new Set(values.filter(Boolean))).sort(); }
async function loadWeek(weekStart: string): Promise<WeekResponse> { const res = await fetch(`${baseUrl()}/api/v1/schedules/week?week_start=${weekStart}`, { headers: await backendHeaders(), cache: "no-store" }); if (!res.ok) throw new Error(`Schedule API failed: ${res.status}`); return res.json(); }
async function loadActuals(weekStart: string): Promise<ScheduleActual[]> { const res = await fetch(`${baseUrl()}/api/v1/schedules/actuals/week?week_start=${weekStart}`, { headers: await backendHeaders(), cache: "no-store" }); if (!res.ok) throw new Error(`Attendance records could not be loaded (${res.status}).`); const data: ActualsResponse = await res.json(); return data.items || []; }
async function loadEmployees(): Promise<ScheduleEmployee[]> { const res = await fetch(`${baseUrl()}/api/v1/schedules/employees`, { headers: await backendHeaders(), cache: "no-store" }); if (!res.ok) throw new Error(`Employees could not be loaded (${res.status}).`); const data = await res.json(); return data.items || []; }
function actualKey(employeeId: number | null | undefined, date: string) { return `${employeeId || "unassigned"}:${date}`; }
function shiftIdentity(shift: ScheduleShift) { return [shift.employee_id || "unassigned", shift.shift_date, shift.start_time, shift.end_time].join(":"); }
function dedupeScheduleItems(items: ScheduleShift[]) { const byIdentity = new Map<string, ScheduleShift>(); for (const item of items) { const key = shiftIdentity(item); const existing = byIdentity.get(key); if (!existing) { byIdentity.set(key, item); continue; } if (existing.source === "imported" && item.source !== "imported") byIdentity.set(key, item); } return Array.from(byIdentity.values()); }
function actualText(shift: ScheduleShift) { if (shift.is_absent) return shift.absence_type || "Absent"; if (shift.actual_in || shift.actual_out) return `${shift.actual_in || "—"}–${shift.actual_out || "—"}`; return "Not recorded"; }
function uniqueText(values: Array<string | null | undefined>) { return Array.from(new Set(values.map((value) => (value || "").trim()).filter(Boolean))).join("; "); }
function scheduleCellText(shifts: ScheduleShift[]) { if (!shifts.length) return "Rest Day / No Shift"; return shifts.map((shift) => `${shift.start_time}–${shift.end_time}${shift.is_overnight ? " +1" : ""}\n${shift.position || "Shift"}`).join("\n\n"); }

export default async function SchedulePage({ searchParams }: { searchParams: Promise<{ week_start?: string; department?: string; position?: string; employee_id?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  const canEditSchedule = true;
  const params = await searchParams;
  const weekStart = params.week_start || mondayOfWeek();
  const selectedDepartment = params.department || "all";
  const selectedPosition = params.position || "all";
  const selectedEmployeeId = params.employee_id || "all";
  const selectedEmployeeNumber = selectedEmployeeId === "all" ? null : Number(selectedEmployeeId);
  const loaded = await Promise.allSettled([loadWeek(weekStart), loadEmployees(), loadActuals(weekStart)]);
  const failed = loaded.find((result) => result.status === "rejected");
  if (failed?.status === "rejected") return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page"><section className="card"><strong>Schedule unavailable</strong><p className="muted">{failed.reason instanceof Error ? failed.reason.message : "Try again shortly."}</p></section></div></Shell>;
  const [week, employees, actuals] = loaded.map((result) => result.status === "fulfilled" ? result.value : null) as [WeekResponse, ScheduleEmployee[], ScheduleActual[]];
  const actualsByKey = actuals.reduce<Record<string, ScheduleActual>>((acc, actual) => { acc[actualKey(actual.employee_id, actual.work_date)] ||= actual; return acc; }, {});
  const days = Array.from({ length: 7 }, (_, i) => addIsoDays(week.week_start, i));
  const previousWeekStart = addWeek(week.week_start, -1);
  const enrichedItems: ScheduleShift[] = dedupeScheduleItems(week.items).map((item) => { const actual = actualsByKey[actualKey(item.employee_id, item.shift_date)]; if (actual) return { ...item, actual_in: actual.actual_in || null, actual_out: actual.actual_out || null, actual_status: actual.attendance_status || null, actual_source: actual.source || null, actual_notes: actual.notes || null, is_absent: actual.is_absent || 0, absence_type: actual.absence_type || null, approved_ot_hours: actual.approved_ot_hours || 0 }; if (item.source === "imported" && item.employee_id) return { ...item, actual_in: item.start_time, actual_out: item.end_time, actual_status: "Approved", actual_source: "legacy_schedule", actual_notes: "Legacy schedule treated as actual for old data.", is_absent: 0, approved_ot_hours: 0 }; return item; });
  const departments = uniq([...employees.map((e) => e.department || ""), ...enrichedItems.map((s) => s.employee_department || s.department || "")]);
  const positions = uniq([...employees.map((e) => e.position || ""), ...enrichedItems.map((s) => s.position || "")]);
  const scheduledEmployeeIds = new Set(enrichedItems.map((item) => item.employee_id).filter((id): id is number => typeof id === "number"));
  const employeeOptions = employees.filter((employee) => scheduledEmployeeIds.has(employee.id) || employees.length <= 80).sort((a, b) => a.full_name.localeCompare(b.full_name));
  const selectedEmployee = selectedEmployeeNumber ? employees.find((employee) => employee.id === selectedEmployeeNumber) : null;
  const filteredItems = enrichedItems.filter((item) => { const employee = item.employee_id ? employees.find((record) => record.id === item.employee_id) : null; const dept = item.employee_department || item.department || employee?.department || ""; const pos = item.position || employee?.position || ""; return (selectedDepartment === "all" || dept === selectedDepartment) && (selectedPosition === "all" || pos === selectedPosition) && (selectedEmployeeNumber == null || item.employee_id === selectedEmployeeNumber); });
  const boardEmployees = employees.filter((employee) => { const byDepartment = selectedDepartment === "all" || employee.department === selectedDepartment; const byPosition = selectedPosition === "all" || employee.position === selectedPosition || filteredItems.some((item) => item.employee_id === employee.id && item.position === selectedPosition); const byEmployee = selectedEmployeeNumber == null || employee.id === selectedEmployeeNumber; return byDepartment && byPosition && byEmployee; }).sort((a, b) => a.full_name.localeCompare(b.full_name));
  const totalHours = filteredItems.reduce((sum, item) => sum + Number(item.planned_paid_hours || 0), 0);
  const actualRecorded = filteredItems.filter((item) => item.actual_in || item.actual_out || item.is_absent || item.actual_source === "legacy_schedule").length;
  const missingActuals = filteredItems.filter((item) => !item.actual_in && !item.actual_out && !item.is_absent && item.actual_source !== "legacy_schedule").length;
  const overnightCount = filteredItems.filter((item) => item.is_overnight).length;
  const selectedEmployeeRows = selectedEmployee ? days.map((day) => ({ day, shifts: filteredItems.filter((item) => item.employee_id === selectedEmployee.id && item.shift_date === day) })) : [];
  const printRows = boardEmployees.map((employee) => ({ employee, days: days.map((day) => filteredItems.filter((item) => item.employee_id === employee.id && item.shift_date === day)) }));
  function filterHref(department: string, position: string, employeeId = selectedEmployeeId, nextWeek = week.week_start) { const q = new URLSearchParams(); q.set("week_start", nextWeek); if (department !== "all") q.set("department", department); if (position !== "all") q.set("position", position); if (employeeId !== "all") q.set("employee_id", employeeId); return `/schedule?${q.toString()}`; }

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className={`page ${pass2.page}`}>
        <header className={pass2.heading}><div><span className="eyebrow">Workforce planning</span><h1>Weekly schedule</h1><p>{week.week_start} to {week.week_end}. Plan shifts, compare actuals, and surface staffing risks from one board.</p></div><div className={pass2.headingActions}><Link className="button secondary" href="/schedule/import">Upload attendance</Link><Link className="button secondary" href="/schedule/requests">Shift requests</Link><Link className="button" href="#add-shift">+ Add shift</Link></div></header>

        <section className={pass2.metrics}><div className={`card ${pass2.metric}`}><strong>{filteredItems.length}</strong><span>Scheduled shifts</span></div><div className={`card ${pass2.metric}`}><strong>{numberText(totalHours)}</strong><span>Planned paid hours</span></div><div className={`card ${pass2.metric}`}><strong>{actualRecorded}</strong><span>Actual records matched</span></div><div className={`card ${pass2.metric}`}><strong>{missingActuals}</strong><span>Missing actual records</span></div></section>

        <section className={`card ${pass2.workspace}`}>
          <div className={pass2.workspaceTop}><div><span className="eyebrow">Week board</span><h2>{selectedEmployee ? selectedEmployee.full_name : "All employees"}</h2><p>{boardEmployees.length} employees · {overnightCount} overnight shift{overnightCount === 1 ? "" : "s"}</p></div><div className={pass2.navActions}><Link className="button secondary" href={filterHref(selectedDepartment, selectedPosition, selectedEmployeeId, previousWeekStart)}>← Previous</Link><Link className="button secondary" href={filterHref(selectedDepartment, selectedPosition, selectedEmployeeId, addWeek(week.week_start, 1))}>Next →</Link><PrintButton label="Print / PDF" />{canEditSchedule ? <ScheduleCopyWeekForm currentWeekStart={week.week_start} previousWeekStart={previousWeekStart} /> : null}</div></div>

          <div className={pass2.filters}><form className={styles.dropdownFilters} method="get"><input name="week_start" type="hidden" value={week.week_start} /><label>Department<select name="department" defaultValue={selectedDepartment}><option value="all">All departments</option>{departments.map((dept) => <option key={dept} value={dept}>{dept}</option>)}</select></label><label>Position<select name="position" defaultValue={selectedPosition}><option value="all">All positions</option>{positions.map((pos) => <option key={pos} value={pos}>{pos}</option>)}</select></label><label>Employee<select name="employee_id" defaultValue={selectedEmployeeId}><option value="all">All employees</option>{employeeOptions.map((employee) => <option key={employee.id} value={String(employee.id)}>{employee.full_name}</option>)}</select></label><button className="button" type="submit">Apply</button>{(selectedDepartment !== "all" || selectedPosition !== "all" || selectedEmployeeId !== "all") ? <Link className="button ghost" href={`/schedule?week_start=${week.week_start}`}>Clear</Link> : null}</form></div>

          <div id="add-shift">{canEditSchedule ? <details className={`card ${styles.compactAddShift} ${styles.addShiftDropdown}`}><summary><strong>+ Add shift</strong><span className="muted">Create one schedule row</span></summary><ScheduleShiftForm weekStart={week.week_start} employees={employees} /></details> : null}</div>
          <div className={pass2.boardArea}><div className={styles.boardScroll}><ScheduleBoardClient days={days} shifts={filteredItems} employees={boardEmployees} canEdit={canEditSchedule} /></div></div>
          <div className={pass2.legend}><span className={pass2.legendItem}><i className={pass2.dot} /> Planned shift</span><span className={pass2.legendItem}><i className={`${pass2.dot} ${pass2.dotWarning}`} /> Missing or pending actual</span><span className={pass2.legendItem}><i className={`${pass2.dot} ${pass2.dotDanger}`} /> Absence or conflict</span><span className={pass2.legendItem}><i className={`${pass2.dot} ${pass2.dotMuted}`} /> Rest day / no shift</span></div>
        </section>

        {selectedEmployee ? <section className="card"><div className="panel-title"><h2>{selectedEmployee.full_name}</h2><Link className="primary-link" href={filterHref(selectedDepartment, selectedPosition, "all")}>Clear employee</Link></div><div className="table-wrap"><table className={styles.employeeScheduleTable}><thead><tr><th>Day</th><th>Scheduled</th><th>Actual</th><th>Hours</th><th>Notes</th></tr></thead><tbody>{selectedEmployeeRows.map(({ day, shifts }) => <tr key={day}><td><strong>{formatIsoDay(day)}</strong><br /><span className="muted">{day}</span></td><td>{shifts.length ? shifts.map((shift) => <div className={styles.quickShift} key={shift.id}><strong>{shift.start_time}–{shift.end_time}{shift.is_overnight ? " +1" : ""}</strong><span>{shift.position}</span></div>) : <span className="muted">Rest Day / No Shift</span>}</td><td>{shifts.length ? shifts.map((shift) => <div className={styles.quickShift} key={shift.id}><strong>{actualText(shift)}</strong><span>{shift.actual_status || (shift.actual_source === "legacy_schedule" ? "Approved · legacy" : "No actual yet")}</span></div>) : <span className="muted">—</span>}</td><td>{shifts.length ? `${numberText(shifts.reduce((sum, shift) => sum + Number(shift.planned_paid_hours || 0), 0))} hrs scheduled` : "—"}</td><td>{uniqueText(shifts.map((shift) => shift.actual_notes || shift.notes)) || "—"}</td></tr>)}</tbody></table></div></section> : null}

        <section className={pass2.utilityGrid}><div>{canEditSchedule ? <SchedulePublishControl weekStart={week.week_start} /> : null}</div><aside className={pass2.sidePanel}><ScheduleRiskPanel days={days} shifts={filteredItems} employees={employees} /><Link className="button secondary" href="/controls">Schedule controls</Link></aside></section>

        <section className={styles.printSchedule}><div className={styles.printHeader}><div><span>Hidden Oasis</span><h2>Weekly Schedule</h2><p>{week.week_start} to {week.week_end}</p></div><div><strong>{selectedDepartment === "all" ? "All Departments" : selectedDepartment}</strong><p>{selectedPosition === "all" ? "All Positions" : selectedPosition}</p></div></div><table className={styles.printTable}><thead><tr><th>Employee</th>{days.map((day) => <th key={day}>{formatIsoDay(day)}<br />{day}</th>)}</tr></thead><tbody>{printRows.map(({ employee, days: rowDays }) => <tr key={employee.id}><td><strong>{employee.full_name}</strong><br /><span>{employee.department || "—"} · {employee.position || "—"}</span></td>{rowDays.map((shifts, index) => <td key={`${employee.id}-${index}`}>{scheduleCellText(shifts)}</td>)}</tr>)}{printRows.length === 0 ? <tr><td colSpan={8}>No scheduled shifts for this filter.</td></tr> : null}</tbody></table></section>
      </div>
    </Shell>
  );
}
