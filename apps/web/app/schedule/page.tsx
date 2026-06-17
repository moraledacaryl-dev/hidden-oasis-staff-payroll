import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";
import { numberText } from "@/lib/api";
import { ScheduleShiftForm } from "@/components/ScheduleShiftForm";
import { ScheduleCopyWeekForm } from "@/components/ScheduleCopyWeekForm";
import { ScheduleBoardClient } from "@/components/ScheduleBoardClient";
import { mondayOfWeek } from "@/lib/period";
import styles from "./page.module.css";

type Shift = { id: number; employee_id: number | null; shift_date: string; start_time: string; end_time: string; position: string; department?: string | null; employee_department?: string | null; break_minutes: number; status: string; notes?: string | null; employee_name?: string | null; planned_paid_hours: number; is_overnight: boolean; source?: string; movable?: boolean };
type WeekResponse = { ok: boolean; week_start: string; week_end: string; items: Shift[]; mode: string };
type ScheduleEmployee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };

function baseUrl() { return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, ""); }
function addDays(iso: string, days: number) { const d = new Date(`${iso}T00:00:00`); d.setDate(d.getDate() + days); return d.toISOString().slice(0, 10); }
function addWeek(iso: string, weeks: number) { return addDays(iso, weeks * 7); }
function uniq(values: string[]) { return Array.from(new Set(values.filter(Boolean))).sort(); }
function dayLabel(iso: string) { return new Date(`${iso}T00:00:00`).toLocaleDateString("en-PH", { weekday: "short", month: "short", day: "numeric" }); }

async function apiHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  const headers: HeadersInit = { Accept: "application/json" };
  const key = process.env.STAFF_PAYROLL_API_KEY;
  if (key) headers["X-API-Key"] = key;
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function loadWeek(weekStart: string): Promise<WeekResponse> {
  const res = await fetch(`${baseUrl()}/api/v1/schedules/week?week_start=${weekStart}`, { headers: await apiHeaders(), cache: "no-store" });
  if (!res.ok) throw new Error(`Schedule API failed: ${res.status}`);
  return res.json();
}

async function loadEmployees(): Promise<ScheduleEmployee[]> {
  const res = await fetch(`${baseUrl()}/api/v1/schedules/employees`, { headers: await apiHeaders(), cache: "no-store" });
  if (!res.ok) return [];
  const data = await res.json().catch(() => ({ items: [] }));
  return data.items || [];
}

export default async function SchedulePage({ searchParams }: { searchParams: Promise<{ week_start?: string; department?: string; position?: string; employee_id?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  }
  const canEditSchedule = session.role_key === "owner" || session.role_key === "payroll";

  const params = await searchParams;
  const weekStart = params.week_start || mondayOfWeek();
  const selectedDepartment = params.department || "all";
  const selectedPosition = params.position || "all";
  const selectedEmployeeId = params.employee_id || "all";
  const selectedEmployeeNumber = selectedEmployeeId === "all" ? null : Number(selectedEmployeeId);

  const [week, employees] = await Promise.all([loadWeek(weekStart), loadEmployees()]);
  const days = Array.from({ length: 7 }, (_, i) => addDays(week.week_start, i));
  const previousWeekStart = addWeek(week.week_start, -1);

  const departments = uniq([...employees.map((e) => e.department || ""), ...week.items.map((s) => s.employee_department || s.department || "")]);
  const positions = uniq([...employees.map((e) => e.position || ""), ...week.items.map((s) => s.position || "")]);
  const scheduledEmployeeIds = new Set(week.items.map((item) => item.employee_id).filter((id): id is number => typeof id === "number"));
  const employeeOptions = employees
    .filter((employee) => scheduledEmployeeIds.has(employee.id) || employees.length <= 80)
    .sort((a, b) => a.full_name.localeCompare(b.full_name));
  const selectedEmployee = selectedEmployeeNumber ? employees.find((employee) => employee.id === selectedEmployeeNumber) : null;

  const filteredItems = week.items.filter((item) => {
    const dept = item.employee_department || item.department || "";
    const byDepartment = selectedDepartment === "all" || dept === selectedDepartment;
    const byPosition = selectedPosition === "all" || item.position === selectedPosition;
    const byEmployee = selectedEmployeeNumber == null || item.employee_id === selectedEmployeeNumber;
    return byDepartment && byPosition && byEmployee;
  });

  const totalHours = filteredItems.reduce((sum, item) => sum + Number(item.planned_paid_hours || 0), 0);
  const unassignedCount = filteredItems.filter((item) => !item.employee_id).length;
  const peopleHours = filteredItems.reduce<Record<string, { id: number | null; shifts: number; hours: number }>>((acc, item) => {
    const person = item.employee_name || "Unassigned";
    acc[person] ||= { id: item.employee_id, shifts: 0, hours: 0 };
    acc[person].shifts += 1;
    acc[person].hours += Number(item.planned_paid_hours || 0);
    return acc;
  }, {});

  const selectedEmployeeRows = selectedEmployee
    ? days.map((day) => ({ day, shifts: filteredItems.filter((item) => item.employee_id === selectedEmployee.id && item.shift_date === day) }))
    : [];

  function filterHref(department: string, position: string, employeeId = selectedEmployeeId, nextWeek = week.week_start) {
    const q = new URLSearchParams();
    q.set("week_start", nextWeek);
    if (department !== "all") q.set("department", department);
    if (position !== "all") q.set("position", position);
    if (employeeId !== "all") q.set("employee_id", employeeId);
    return `/schedule?${q.toString()}`;
  }

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Schedule</span><h1>{week.week_start} to {week.week_end}</h1><p className="muted">{canEditSchedule ? "Click any shift or empty day to manage schedule, actual attendance, and leave." : "Supervisor schedule view. Editing controls are hidden."}</p></div>
          <StatusBadge label="planned" tone="warning" />
        </header>

        <section className={styles.toolbar}>
          <Link className="primary-link" href={filterHref(selectedDepartment, selectedPosition, selectedEmployeeId, previousWeekStart)}>Prev</Link>
          <Link className="primary-link" href={filterHref(selectedDepartment, selectedPosition, selectedEmployeeId, addWeek(week.week_start, 1))}>Next</Link>
          {canEditSchedule ? <ScheduleCopyWeekForm currentWeekStart={week.week_start} previousWeekStart={previousWeekStart} /> : null}
          {canEditSchedule ? <Link className="primary-link" href="/controls">Controls</Link> : null}
        </section>

        <section className="grid cols-3"><div className="card metric"><span className="eyebrow">Shifts</span><strong className="metric-value">{filteredItems.length}</strong></div><div className="card metric"><span className="eyebrow">Hours</span><strong className="metric-value">{numberText(totalHours)}</strong></div><div className="card metric"><span className="eyebrow">Unassigned</span><strong className="metric-value">{unassignedCount}</strong></div></section>

        <section className="card"><div className={styles.filterGrid}><div><strong>Department</strong><div className={styles.chips}><Link className={selectedDepartment === "all" ? styles.activeChip : styles.chip} href={filterHref("all", selectedPosition)}>All</Link>{departments.map((dept) => (<Link className={selectedDepartment === dept ? styles.activeChip : styles.chip} href={filterHref(dept, selectedPosition)} key={dept}>{dept}</Link>))}</div></div><div><strong>Position</strong><div className={styles.chips}><Link className={selectedPosition === "all" ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, "all")}>All</Link>{positions.map((pos) => (<Link className={selectedPosition === pos ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, pos)} key={pos}>{pos}</Link>))}</div></div><div className={styles.employeeFilter}><strong>Employee</strong><div className={styles.chips}><Link className={selectedEmployeeId === "all" ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, selectedPosition, "all")}>All</Link>{employeeOptions.map((employee) => (<Link className={selectedEmployeeId === String(employee.id) ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, selectedPosition, String(employee.id))} key={employee.id}>{employee.full_name}</Link>))}</div></div></div></section>

        <section className="grid cols-2">{canEditSchedule ? <div className="card"><div className="panel-title"><h2>Add shift</h2></div><ScheduleShiftForm weekStart={week.week_start} employees={employees} /></div> : null}<div className="card"><div className="panel-title"><h2>People</h2></div><div className={styles.peopleList}>{Object.entries(peopleHours).length ? Object.entries(peopleHours).map(([person, stats]) => (<Link className={styles.personRow} key={person} href={stats.id ? filterHref(selectedDepartment, selectedPosition, String(stats.id)) : filterHref(selectedDepartment, selectedPosition, "all")}><strong>{person}</strong><span>{stats.shifts} · {numberText(stats.hours)} hrs</span></Link>)) : <p className="muted">No scheduled people yet.</p>}</div></div></section>

        {selectedEmployee ? (
          <section className="card">
            <div className="panel-title"><div><h2>{selectedEmployee.full_name}</h2><p className="muted">Quick vertical schedule for this week.</p></div><Link className="primary-link" href={filterHref(selectedDepartment, selectedPosition, "all")}>Clear employee</Link></div>
            <div className="table-wrap">
              <table className={styles.employeeScheduleTable}>
                <thead><tr><th>Day</th><th>Schedule</th><th>Hours</th><th>Notes</th></tr></thead>
                <tbody>
                  {selectedEmployeeRows.map(({ day, shifts }) => (
                    <tr key={day}>
                      <td><strong>{dayLabel(day)}</strong><br /><span className="muted">{day}</span></td>
                      <td>{shifts.length ? shifts.map((shift) => (<div className={styles.quickShift} key={shift.id}><strong>{shift.start_time}–{shift.end_time}{shift.is_overnight ? " +1" : ""}</strong><span>{shift.position}</span></div>)) : <span className="muted">No shift</span>}</td>
                      <td>{shifts.length ? `${numberText(shifts.reduce((sum, shift) => sum + Number(shift.planned_paid_hours || 0), 0))} hrs` : "—"}</td>
                      <td>{shifts.map((shift) => shift.notes).filter(Boolean).join("; ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        <section className="card"><div className="panel-title"><h2>Week</h2></div><div className={styles.boardScroll}><ScheduleBoardClient days={days} shifts={filteredItems} employees={employees} canEdit={canEditSchedule} /></div></section>
      </div>
    </Shell>
  );
}
