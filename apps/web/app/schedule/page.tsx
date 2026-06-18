import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";
import { numberText } from "@/lib/api";
import { ScheduleShiftForm } from "@/components/ScheduleShiftForm";
import { ScheduleCopyWeekForm } from "@/components/ScheduleCopyWeekForm";
import { ScheduleBoardClient } from "@/components/ScheduleBoardClient";
import { ScheduleRiskPanel } from "@/components/ScheduleRiskPanel";
import { mondayOfWeek } from "@/lib/period";
import styles from "./page.module.css";

type Shift = { id: number; employee_id: number | null; shift_date: string; start_time: string; end_time: string; position: string; department?: string | null; employee_department?: string | null; break_minutes: number; status: string; notes?: string | null; employee_name?: string | null; planned_paid_hours: number; is_overnight: boolean; source?: string; movable?: boolean; actual_in?: string | null; actual_out?: string | null; actual_status?: string | null; actual_source?: string | null; actual_notes?: string | null; is_absent?: number | null; absence_type?: string | null; approved_ot_hours?: number | null };
type ActualLog = { id: number; employee_id: number; work_date: string; actual_in?: string | null; actual_out?: string | null; attendance_status?: string | null; approved_ot_hours?: number | null; is_absent?: number | null; absence_type?: string | null; source?: string | null; verification_type?: string | null; notes?: string | null; employee_name?: string | null };
type WeekResponse = { ok: boolean; week_start: string; week_end: string; items: Shift[]; mode: string };
type ActualsResponse = { ok: boolean; week_start: string; week_end: string; items: ActualLog[]; mode: string };
type ScheduleEmployee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };

function baseUrl() { return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, ""); }
function addDays(iso: string, days: number) { const d = new Date(`${iso}T00:00:00`); d.setDate(d.getDate() + days); return d.toISOString().slice(0, 10); }
function addWeek(iso: string, weeks: number) { return addDays(iso, weeks * 7); }
function uniq(values: string[]) { return Array.from(new Set(values.filter(Boolean))).sort(); }
function dayLabel(iso: string) { return new Date(`${iso}T00:00:00`).toLocaleDateString("en-PH", { weekday: "short", month: "short", day: "numeric" }); }
async function apiHeaders(): Promise<HeadersInit> { const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value; const headers: HeadersInit = { Accept: "application/json" }; const key = process.env.STAFF_PAYROLL_API_KEY; if (key) headers["X-API-Key"] = key; if (token) headers.Authorization = `Bearer ${token}`; return headers; }
async function loadWeek(weekStart: string): Promise<WeekResponse> { const res = await fetch(`${baseUrl()}/api/v1/schedules/week?week_start=${weekStart}`, { headers: await apiHeaders(), cache: "no-store" }); if (!res.ok) throw new Error(`Schedule API failed: ${res.status}`); return res.json(); }
async function loadActuals(weekStart: string): Promise<ActualLog[]> { const res = await fetch(`${baseUrl()}/api/v1/schedules/actuals/week?week_start=${weekStart}`, { headers: await apiHeaders(), cache: "no-store" }); if (!res.ok) return []; const data: ActualsResponse = await res.json().catch(() => ({ ok: false, week_start: weekStart, week_end: weekStart, items: [], mode: "error" })); return data.items || []; }
async function loadEmployees(): Promise<ScheduleEmployee[]> { const res = await fetch(`${baseUrl()}/api/v1/schedules/employees`, { headers: await apiHeaders(), cache: "no-store" }); if (!res.ok) return []; const data = await res.json().catch(() => ({ items: [] })); return data.items || []; }
function actualKey(employeeId: number | null | undefined, date: string) { return `${employeeId || "unassigned"}:${date}`; }
function shiftIdentity(shift: Shift) { return [shift.employee_id || "unassigned", shift.shift_date, shift.start_time, shift.end_time].join(":"); }
function dedupeScheduleItems(items: Shift[]) { const byIdentity = new Map<string, Shift>(); for (const item of items) { const key = shiftIdentity(item); const existing = byIdentity.get(key); if (!existing) { byIdentity.set(key, item); continue; } if (existing.source === "imported" && item.source !== "imported") byIdentity.set(key, item); } return Array.from(byIdentity.values()); }
function actualText(shift: Shift) { if (shift.is_absent) return shift.absence_type || "Absent"; if (shift.actual_in || shift.actual_out) return `${shift.actual_in || "—"}–${shift.actual_out || "—"}`; return "Not recorded"; }
function uniqueText(values: Array<string | null | undefined>) { return Array.from(new Set(values.map((value) => (value || "").trim()).filter(Boolean))).join("; "); }
function scheduleCellText(shifts: Shift[]) { if (!shifts.length) return "Rest Day / No Shift"; return shifts.map((shift) => `${shift.start_time}–${shift.end_time}${shift.is_overnight ? " +1" : ""}\n${shift.position || "Shift"}`).join("\n\n"); }

export default async function SchedulePage({ searchParams }: { searchParams: Promise<{ week_start?: string; department?: string; position?: string; employee_id?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  const canEditSchedule = session.role_key === "owner" || session.role_key === "payroll";
  const params = await searchParams;
  const weekStart = params.week_start || mondayOfWeek();
  const selectedDepartment = params.department || "all";
  const selectedPosition = params.position || "all";
  const selectedEmployeeId = params.employee_id || "all";
  const selectedEmployeeNumber = selectedEmployeeId === "all" ? null : Number(selectedEmployeeId);
  const [week, employees, actuals] = await Promise.all([loadWeek(weekStart), loadEmployees(), loadActuals(weekStart)]);
  const actualsByKey = actuals.reduce<Record<string, ActualLog>>((acc, actual) => { acc[actualKey(actual.employee_id, actual.work_date)] ||= actual; return acc; }, {});
  const days = Array.from({ length: 7 }, (_, i) => addDays(week.week_start, i));
  const previousWeekStart = addWeek(week.week_start, -1);
  const enrichedItems: Shift[] = dedupeScheduleItems(week.items).map((item) => { const actual = actualsByKey[actualKey(item.employee_id, item.shift_date)]; if (actual) return { ...item, actual_in: actual.actual_in || null, actual_out: actual.actual_out || null, actual_status: actual.attendance_status || null, actual_source: actual.source || null, actual_notes: actual.notes || null, is_absent: actual.is_absent || 0, absence_type: actual.absence_type || null, approved_ot_hours: actual.approved_ot_hours || 0 }; if (item.source === "imported" && item.employee_id) return { ...item, actual_in: item.start_time, actual_out: item.end_time, actual_status: "Approved", actual_source: "legacy_schedule", actual_notes: "Legacy schedule treated as actual for old data.", is_absent: 0, approved_ot_hours: 0 }; return item; });
  const departments = uniq([...employees.map((e) => e.department || ""), ...enrichedItems.map((s) => s.employee_department || s.department || "")]);
  const positions = uniq([...employees.map((e) => e.position || ""), ...enrichedItems.map((s) => s.position || "")]);
  const scheduledEmployeeIds = new Set(enrichedItems.map((item) => item.employee_id).filter((id): id is number => typeof id === "number"));
  const employeeOptions = employees.filter((employee) => scheduledEmployeeIds.has(employee.id) || employees.length <= 80).sort((a, b) => a.full_name.localeCompare(b.full_name));
  const selectedEmployee = selectedEmployeeNumber ? employees.find((employee) => employee.id === selectedEmployeeNumber) : null;
  const filteredItems = enrichedItems.filter((item) => { const employee = item.employee_id ? employees.find((record) => record.id === item.employee_id) : null; const dept = item.employee_department || item.department || employee?.department || ""; const pos = item.position || employee?.position || ""; return (selectedDepartment === "all" || dept === selectedDepartment) && (selectedPosition === "all" || pos === selectedPosition) && (selectedEmployeeNumber == null || item.employee_id === selectedEmployeeNumber); });
  const boardEmployeeIds = new Set(filteredItems.map((item) => item.employee_id).filter((id): id is number => typeof id === "number"));
  const boardEmployees = employees.filter((employee) => { const byDepartment = selectedDepartment === "all" || employee.department === selectedDepartment; const byPosition = selectedPosition === "all" || employee.position === selectedPosition || filteredItems.some((item) => item.employee_id === employee.id && item.position === selectedPosition); const byEmployee = selectedEmployeeNumber == null || employee.id === selectedEmployeeNumber; return byDepartment && byPosition && byEmployee && (boardEmployeeIds.has(employee.id) || selectedEmployeeNumber === employee.id); }).sort((a, b) => a.full_name.localeCompare(b.full_name));
  const totalHours = filteredItems.reduce((sum, item) => sum + Number(item.planned_paid_hours || 0), 0);
  const actualRecorded = filteredItems.filter((item) => item.actual_in || item.actual_out || item.is_absent || item.actual_source === "legacy_schedule").length;
  const selectedEmployeeRows = selectedEmployee ? days.map((day) => ({ day, shifts: filteredItems.filter((item) => item.employee_id === selectedEmployee.id && item.shift_date === day) })) : [];
  const printRows = boardEmployees.map((employee) => ({ employee, days: days.map((day) => filteredItems.filter((item) => item.employee_id === employee.id && item.shift_date === day)) }));
  function filterHref(department: string, position: string, employeeId = selectedEmployeeId, nextWeek = week.week_start) { const q = new URLSearchParams(); q.set("week_start", nextWeek); if (department !== "all") q.set("department", department); if (position !== "all") q.set("position", position); if (employeeId !== "all") q.set("employee_id", employeeId); return `/schedule?${q.toString()}`; }

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Schedule</span><h1>{week.week_start} to {week.week_end}</h1><p className="muted">Scheduled and actual attendance are shown together.</p></div><div className="badge-row"><StatusBadge label="planned + actual" tone="warning" /><PrintButton label="Download landscape" /></div></header>
        <section className={styles.toolbar}><Link className="primary-link" href={filterHref(selectedDepartment, selectedPosition, selectedEmployeeId, previousWeekStart)}>Prev</Link><Link className="primary-link" href={filterHref(selectedDepartment, selectedPosition, selectedEmployeeId, addWeek(week.week_start, 1))}>Next</Link><PrintButton label="Print / Save PDF" />{canEditSchedule ? <ScheduleCopyWeekForm currentWeekStart={week.week_start} previousWeekStart={previousWeekStart} /> : null}{canEditSchedule ? <Link className="primary-link" href="/controls">Controls</Link> : null}</section>
        <section className={`${styles.screenOnly} grid cols-3`}><div className="card metric"><span className="eyebrow">Shifts</span><strong className="metric-value">{filteredItems.length}</strong></div><div className="card metric"><span className="eyebrow">Scheduled Hours</span><strong className="metric-value">{numberText(totalHours)}</strong></div><div className="card metric"><span className="eyebrow">Actual Records</span><strong className="metric-value">{actualRecorded}</strong></div></section>
        <ScheduleRiskPanel days={days} shifts={filteredItems} employees={employees} />
        <section className={`${styles.screenOnly} card`}><div className={styles.filterGrid}><div><strong>Department</strong><div className={styles.chips}><Link className={selectedDepartment === "all" ? styles.activeChip : styles.chip} href={filterHref("all", selectedPosition)}>All</Link>{departments.map((dept) => (<Link className={selectedDepartment === dept ? styles.activeChip : styles.chip} href={filterHref(dept, selectedPosition)} key={dept}>{dept}</Link>))}</div></div><div><strong>Position</strong><div className={styles.chips}><Link className={selectedPosition === "all" ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, "all")}>All</Link>{positions.map((pos) => (<Link className={selectedPosition === pos ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, pos)} key={pos}>{pos}</Link>))}</div></div><div className={styles.employeeFilter}><strong>Employee</strong><div className={styles.chips}><Link className={selectedEmployeeId === "all" ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, selectedPosition, "all")}>All</Link>{employeeOptions.map((employee) => (<Link className={selectedEmployeeId === String(employee.id) ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, selectedPosition, String(employee.id))} key={employee.id}>{employee.full_name}</Link>))}</div></div></div></section>
        {canEditSchedule ? <section className={`card ${styles.compactAddShift}`}><div className="panel-title"><h2>Add shift</h2><p className="muted">Use this only when adding a new scheduled shift.</p></div><ScheduleShiftForm weekStart={week.week_start} employees={employees} /></section> : null}
        <section className={`card ${styles.screenSchedule}`}><div className="panel-title"><h2>Week</h2><p className="muted">Drag-and-drop board is filtered by the selected department, position, and employee.</p></div><div className={styles.boardScroll}><ScheduleBoardClient days={days} shifts={filteredItems} employees={boardEmployees} canEdit={canEditSchedule} /></div></section>
        <section className={styles.printSchedule}><div className={styles.printHeader}><div><span>Hidden Oasis</span><h2>Weekly Schedule</h2><p>{week.week_start} to {week.week_end}</p></div><div><strong>{selectedDepartment === "all" ? "All Departments" : selectedDepartment}</strong><p>{selectedPosition === "all" ? "All Positions" : selectedPosition}</p></div></div><table className={styles.printTable}><thead><tr><th>Employee</th>{days.map((day) => <th key={day}>{dayLabel(day)}<br />{day}</th>)}</tr></thead><tbody>{printRows.map(({ employee, days: rowDays }) => <tr key={employee.id}><td><strong>{employee.full_name}</strong><br /><span>{employee.department || "—"} · {employee.position || "—"}</span></td>{rowDays.map((shifts, index) => <td key={`${employee.id}-${index}`}>{scheduleCellText(shifts)}</td>)}</tr>)}{printRows.length === 0 ? <tr><td colSpan={8}>No scheduled shifts for this filter.</td></tr> : null}</tbody></table></section>
        {selectedEmployee ? <section className={`${styles.screenOnly} card`}><div className="panel-title"><div><h2>{selectedEmployee.full_name}</h2><p className="muted">Vertical schedule versus actual for this week.</p></div><Link className="primary-link" href={filterHref(selectedDepartment, selectedPosition, "all")}>Clear employee</Link></div><div className="table-wrap"><table className={styles.employeeScheduleTable}><thead><tr><th>Day</th><th>Scheduled</th><th>Actual</th><th>Hours</th><th>Notes</th></tr></thead><tbody>{selectedEmployeeRows.map(({ day, shifts }) => <tr key={day}><td><strong>{dayLabel(day)}</strong><br /><span className="muted">{day}</span></td><td>{shifts.length ? shifts.map((shift) => <div className={styles.quickShift} key={shift.id}><strong>{shift.start_time}–{shift.end_time}{shift.is_overnight ? " +1" : ""}</strong><span>{shift.position}</span></div>) : <span className="muted">Rest Day / No Shift</span>}</td><td>{shifts.length ? shifts.map((shift) => <div className={styles.quickShift} key={shift.id}><strong>{actualText(shift)}</strong><span>{shift.actual_status || (shift.actual_source === "legacy_schedule" ? "Approved · legacy" : "No actual yet")}</span></div>) : <span className="muted">—</span>}</td><td>{shifts.length ? `${numberText(shifts.reduce((sum, shift) => sum + Number(shift.planned_paid_hours || 0), 0))} hrs scheduled` : "—"}</td><td>{uniqueText(shifts.map((shift) => shift.actual_notes || shift.notes)) || "—"}</td></tr>)}</tbody></table></div></section> : null}
      </div>
    </Shell>
  );
}
