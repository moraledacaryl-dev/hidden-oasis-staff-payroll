import Link from "next/link";
import { cookies } from "next/headers";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { numberText } from "@/lib/api";
import { ScheduleShiftForm } from "@/components/ScheduleShiftForm";
import styles from "./page.module.css";

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
};

type WeekResponse = {
  ok: boolean;
  week_start: string;
  week_end: string;
  items: Shift[];
  mode: string;
};

type ScheduleEmployee = {
  id: number;
  full_name: string;
  employee_code?: string;
  department?: string;
  position?: string;
};

function baseUrl() {
  return (
    process.env.STAFF_PAYROLL_API_URL ||
    process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL ||
    "http://127.0.0.1:8001"
  ).replace(/\/$/, "");
}

function addDays(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function addWeek(iso: string, weeks: number) {
  return addDays(iso, weeks * 7);
}

function label(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-PH", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function uniq(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort();
}

async function apiHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  const headers: HeadersInit = { Accept: "application/json" };
  const key =
    process.env.STAFF_PAYROLL_API_KEY ||
    process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_KEY;

  if (key) headers["X-API-Key"] = key;
  if (token) headers.Authorization = `Bearer ${token}`;

  return headers;
}

async function loadWeek(weekStart: string): Promise<WeekResponse> {
  const res = await fetch(
    `${baseUrl()}/api/v1/schedules/week?week_start=${weekStart}`,
    {
      headers: await apiHeaders(),
      cache: "no-store",
    }
  );

  if (!res.ok) throw new Error(`Schedule API failed: ${res.status}`);

  return res.json();
}

async function loadEmployees(): Promise<ScheduleEmployee[]> {
  const res = await fetch(`${baseUrl()}/api/v1/schedules/employees`, {
    headers: await apiHeaders(),
    cache: "no-store",
  });

  if (!res.ok) return [];

  const data = await res.json().catch(() => ({ items: [] }));
  return data.items || [];
}

export default async function SchedulePage({
  searchParams,
}: {
  searchParams: Promise<{
    week_start?: string;
    department?: string;
    position?: string;
  }>;
}) {
  const params = await searchParams;
  const weekStart = params.week_start || "2026-06-15";
  const selectedDepartment = params.department || "all";
  const selectedPosition = params.position || "all";

  const [week, employees] = await Promise.all([
    loadWeek(weekStart),
    loadEmployees(),
  ]);

  const days = Array.from({ length: 7 }, (_, i) =>
    addDays(week.week_start, i)
  );

  const departments = uniq([
    ...employees.map((e) => e.department || ""),
    ...week.items.map((s) => s.employee_department || s.department || ""),
  ]);

  const positions = uniq([
    ...employees.map((e) => e.position || ""),
    ...week.items.map((s) => s.position || ""),
  ]);

  const filteredItems = week.items.filter((item) => {
    const dept = item.employee_department || item.department || "";
    const byDepartment =
      selectedDepartment === "all" || dept === selectedDepartment;
    const byPosition =
      selectedPosition === "all" || item.position === selectedPosition;
    return byDepartment && byPosition;
  });

  const totalHours = filteredItems.reduce(
    (sum, item) => sum + Number(item.planned_paid_hours || 0),
    0
  );

  const assignedCount = filteredItems.filter((item) => item.employee_id).length;
  const unassignedCount = filteredItems.length - assignedCount;

  const visiblePeople = uniq(
    filteredItems.map((item) => item.employee_name || "Unassigned")
  );

  function filterHref(
    department: string,
    position: string,
    nextWeek = week.week_start
  ) {
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
          <div className="grid">
            <span className="eyebrow">Schedule Board</span>
            <h1>
              {week.week_start} to {week.week_end}
            </h1>
            <p className="muted">
              Sling-style weekly schedule board. Planned hours are only the
              baseline before attendance, leave, and approved OT.
            </p>
          </div>
          <StatusBadge label="planned only" tone="warning" />
        </header>

        <section className={styles.toolbar}>
          <Link
            className="primary-link"
            href={filterHref(
              selectedDepartment,
              selectedPosition,
              addWeek(week.week_start, -1)
            )}
          >
            Previous week
          </Link>
          <Link
            className="primary-link"
            href={filterHref(
              selectedDepartment,
              selectedPosition,
              addWeek(week.week_start, 1)
            )}
          >
            Next week
          </Link>
          <Link className="primary-link" href="/controls">
            Controls
          </Link>
        </section>

        <section className="grid cols-3">
          <div className="card metric">
            <span className="eyebrow">Visible shifts</span>
            <strong className="metric-value">{filteredItems.length}</strong>
          </div>
          <div className="card metric">
            <span className="eyebrow">Planned paid hours</span>
            <strong className="metric-value">{numberText(totalHours)}</strong>
          </div>
          <div className="card metric">
            <span className="eyebrow">Unassigned</span>
            <strong className="metric-value">{unassignedCount}</strong>
          </div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Filters</h2>
              <p className="muted">Filter without changing schedule data.</p>
            </div>
          </div>

          <div className={styles.filterGrid}>
            <div>
              <strong>Department</strong>
              <div className={styles.chips}>
                <Link
                  className={
                    selectedDepartment === "all"
                      ? styles.activeChip
                      : styles.chip
                  }
                  href={filterHref("all", selectedPosition)}
                >
                  All
                </Link>
                {departments.map((dept) => (
                  <Link
                    className={
                      selectedDepartment === dept
                        ? styles.activeChip
                        : styles.chip
                    }
                    href={filterHref(dept, selectedPosition)}
                    key={dept}
                  >
                    {dept}
                  </Link>
                ))}
              </div>
            </div>

            <div>
              <strong>Position</strong>
              <div className={styles.chips}>
                <Link
                  className={
                    selectedPosition === "all"
                      ? styles.activeChip
                      : styles.chip
                  }
                  href={filterHref(selectedDepartment, "all")}
                >
                  All
                </Link>
                {positions.map((pos) => (
                  <Link
                    className={
                      selectedPosition === pos
                        ? styles.activeChip
                        : styles.chip
                    }
                    href={filterHref(selectedDepartment, pos)}
                    key={pos}
                  >
                    {pos}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="grid cols-2">
          <div className="card">
            <div className="panel-title">
              <div>
                <h2>Add planned shift</h2>
                <p className="muted">
                  Creates a scheduled baseline only. It does not create payroll,
                  time logs, OT, or released pay.
                </p>
              </div>
            </div>
            <ScheduleShiftForm
              weekStart={week.week_start}
              employees={employees}
            />
          </div>

          <div className="card">
            <div className="panel-title">
              <div>
                <h2>People visible</h2>
                <p className="muted">Filtered employees for this week.</p>
              </div>
            </div>

            <div className={styles.peopleList}>
              {visiblePeople.length ? (
                visiblePeople.map((person) => (
                  <div className={styles.personRow} key={person}>
                    <strong>{person}</strong>
                    <span>scheduled</span>
                  </div>
                ))
              ) : (
                <p className="muted">No scheduled people yet.</p>
              )}
            </div>
          </div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Week view</h2>
              <p className="muted">
                Filtered calendar view. Drag-and-drop comes after this board
                structure is stable.
              </p>
            </div>
          </div>

          <div className={styles.scheduleGrid}>
            {days.map((day) => {
              const shifts = filteredItems.filter(
                (item) => item.shift_date === day
              );
              const dayHours = shifts.reduce(
                (sum, item) => sum + Number(item.planned_paid_hours || 0),
                0
              );

              return (
                <div className={styles.scheduleDay} key={day}>
                  <div className={styles.scheduleDayHead}>
                    <div>
                      <strong>{label(day)}</strong>
                      <span>{numberText(dayHours)} hrs</span>
                    </div>
                    <span>
                      {shifts.length} shift{shifts.length === 1 ? "" : "s"}
                    </span>
                  </div>

                  <div className={styles.scheduleStack}>
                    {shifts.map((shift) => (
                      <div className={styles.shiftCard} key={shift.id}>
                        <div className={styles.shiftTop}>
                          <strong>
                            {shift.employee_name || "Unassigned"}
                          </strong>
                          <span>{shift.position}</span>
                        </div>
                        <span>
                          {shift.start_time}–{shift.end_time}
                          {shift.is_overnight ? " +1" : ""}
                        </span>
                        <span>
                          {numberText(shift.planned_paid_hours)} paid hrs ·
                          break {shift.break_minutes}m
                        </span>
                        <span>
                          {shift.employee_department ||
                            shift.department ||
                            "No department"}
                        </span>
                        {shift.notes ? (
                          <p className="muted">{shift.notes}</p>
                        ) : null}
                      </div>
                    ))}

                    {shifts.length === 0 ? (
                      <div className={styles.emptyDay}>No shifts</div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </Shell>
  );
}
