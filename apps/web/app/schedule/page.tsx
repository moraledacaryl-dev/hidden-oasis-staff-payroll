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
import styles from "./page.module.css";

type Shift = { id: number; employee_id: number | null; shift_date: string; start_time: string; end_time: string; position: string; department?: string | null; employee_department?: string | null; break_minutes: number; status: string; notes?: string | null; employee_name?: string | null; planned_paid_hours: number; is_overnight: boolean };
type WeekResponse = { ok: boolean; week_start: string; week_end: string; items: Shift[]; mode: string };
type ScheduleEmployee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };

function baseUrl() { return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, ""); }
function addDays(iso: string, days: number) { const d = new Date(`${iso}T00:00:00`); d.setDate(d.getDate() + days); return d.toISOString().slice(0, 10); }
function addWeek(iso: string, weeks: number) { return addDays(iso, weeks * 7); }
function uniq(values: string[]) { return Array.from(new Set(values.filter(Boolean))).sort(); }

async function apiHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  const headers: HeadersInit = { Accept: "application/json" };
  const key = process.env.STAFF_PAYROLL_API_KEY || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_KEY;
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

export default async function SchedulePage({ searchParams }: { searchParams: Promise<{ week_start?: string; department?: string; position?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");

  const params = await searchParams;
  const weekStart = params.week_start || "2026-06-15";
  const selectedDepartment = params.department || "all";
  const selectedPosition = params.position || "all";

  const [week, employees] = await Promise.all([loadWeek(weekStart), loadEmployees()]);
  const days = Array.from({ length: 7 }, (_, i) => addDays(week.week_start, i));
  const previousWeekStart = addWeek(week.week_start, -1);

  const departments = uniq([...employees.map((e) => e.department || ""), ...week.items.map((s) => s.employee_department || s.department || "")]);
  const positions = uniq([...employees.map((e) => e.position || ""), ...week.items.map((s) => s.position || "")]);

  const filteredItems = week.items.filter((item) => {
    const dept = item.employee_department || item.department || "";
    const byDepartment = selectedDepartment === "all" || dept === selectedDepartment;
    const byPosition = selectedPosition === "all" || item.position === selectedPosition;
    return byDepartment && byPosition;
  });

  const totalHours = filteredItems.reduce((sum, item) => sum + Number(item.planned_paid_hours || 0), 0);
  const unassignedCount = filteredItems.filter((item) => !item.employee_id).length;
  const peopleHours = filteredItems.reduce<Record<string, { shifts: number; hours: number }>>((acc, item) => {
    const person = item.employee_name || "Unassigned";
    acc[person] ||= { shifts: 0, hours: 0 };
    acc[person].shifts += 1;
    acc[person].hours += Number(item.planned_paid_hours || 0);
    return acc;
  }, {});

  function filterHref(department: string, position: string, nextWeek = week.week_start) {
    const q = new URLSearchParams();
    q.set("week_start", nextWeek);
    if (department !== "all") q.set("department", department);
    if (position !== "all") q.set("position", position);
    return `/schedule?${q.toString()}`;
  }

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Schedule</span><h1>{week.week_start} to {week.week_end}</h1><p className="muted">Planned shifts only. Drag cards to move days.</p></div>
          <StatusBadge label="planned" tone="warning" />
        </header>

        <section className={styles.toolbar}>
          <Link className="primary-link" href={filterHref(selectedDepartment, selectedPosition, previousWeekStart)}>Prev</Link>
          <Link className="primary-link" href={filterHref(selectedDepartment, selectedPosition, addWeek(week.week_start, 1))}>Next</Link>
          <ScheduleCopyWeekForm currentWeekStart={week.week_start} previousWeekStart={previousWeekStart} />
          <Link className="primary-link" href="/controls">Controls</Link>
        </section>

        <section className="grid cols-3"><div className="card metric"><span className="eyebrow">Shifts</span><strong className="metric-value">{filteredItems.length}</strong></div><div className="card metric"><span className="eyebrow">Hours</span><strong className="metric-value">{numberText(totalHours)}</strong></div><div className="card metric"><span className="eyebrow">Unassigned</span><strong className="metric-value">{unassignedCount}</strong></div></section>

        <section className="card"><div className={styles.filterGrid}><div><strong>Department</strong><div className={styles.chips}><Link className={selectedDepartment === "all" ? styles.activeChip : styles.chip} href={filterHref("all", selectedPosition)}>All</Link>{departments.map((dept) => (<Link className={selectedDepartment === dept ? styles.activeChip : styles.chip} href={filterHref(dept, selectedPosition)} key={dept}>{dept}</Link>))}</div></div><div><strong>Position</strong><div className={styles.chips}><Link className={selectedPosition === "all" ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, "all")}>All</Link>{positions.map((pos) => (<Link className={selectedPosition === pos ? styles.activeChip : styles.chip} href={filterHref(selectedDepartment, pos)} key={pos}>{pos}</Link>))}</div></div></div></section>

        <section className="grid cols-2"><div className="card"><div className="panel-title"><h2>Add shift</h2></div><ScheduleShiftForm weekStart={week.week_start} employees={employees} /></div><div className="card"><div className="panel-title"><h2>People</h2></div><div className={styles.peopleList}>{Object.entries(peopleHours).length ? Object.entries(peopleHours).map(([person, stats]) => (<div className={styles.personRow} key={person}><strong>{person}</strong><span>{stats.shifts} · {numberText(stats.hours)} hrs</span></div>)) : <p className="muted">No scheduled people yet.</p>}</div></div></section>

        <section className="card"><div className="panel-title"><h2>Week</h2></div><ScheduleBoardClient days={days} shifts={filteredItems} /></section>
      </div>
    </Shell>
  );
}
