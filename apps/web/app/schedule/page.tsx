import { cookies } from "next/headers";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { numberText } from "@/lib/api";

type Shift = { id:number; employee_id:number|null; shift_date:string; start_time:string; end_time:string; position:string; department?:string|null; break_minutes:number; status:string; notes?:string|null; employee_name?:string|null; planned_paid_hours:number; is_overnight:boolean };
type WeekResponse = { ok:boolean; week_start:string; week_end:string; items:Shift[]; mode:string };

function baseUrl(){ return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, ""); }
function addDays(iso:string, days:number){ const d = new Date(`${iso}T00:00:00`); d.setDate(d.getDate()+days); return d.toISOString().slice(0,10); }
function label(iso:string){ return new Date(`${iso}T00:00:00`).toLocaleDateString("en-PH", { weekday:"short", month:"short", day:"numeric" }); }

async function loadWeek(weekStart:string): Promise<WeekResponse> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  const headers: HeadersInit = { Accept: "application/json" };
  const key = process.env.STAFF_PAYROLL_API_KEY || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_KEY;
  if (key) headers["X-API-Key"] = key;
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${baseUrl()}/api/v1/schedules/week?week_start=${weekStart}`, { headers, cache: "no-store" });
  if (!res.ok) throw new Error(`Schedule API failed: ${res.status}`);
  return res.json();
}

export default async function SchedulePage({ searchParams }: { searchParams: Promise<{ week_start?: string }> }) {
  const params = await searchParams;
  const weekStart = params.week_start || "2026-06-15";
  const week = await loadWeek(weekStart);
  const days = Array.from({ length: 7 }, (_, i) => addDays(week.week_start, i));
  const totalHours = week.items.reduce((sum, item) => sum + Number(item.planned_paid_hours || 0), 0);
  const positions = new Set(week.items.map((item) => item.position));

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header"><div className="grid"><span className="eyebrow">Schedule Calendar</span><h1>{week.week_start} to {week.week_end}</h1><p className="muted">Sling-style weekly schedule foundation. Planned paid hours are baseline only and do not create payroll.</p></div><StatusBadge label="planned only" tone="warning" /></header>
        <section className="grid cols-3"><div className="card metric"><span className="eyebrow">Shifts</span><strong className="metric-value">{week.items.length}</strong></div><div className="card metric"><span className="eyebrow">Planned paid hours</span><strong className="metric-value">{numberText(totalHours)}</strong></div><div className="card metric"><span className="eyebrow">Positions</span><strong className="metric-value">{positions.size}</strong></div></section>
        <section className="card"><div className="panel-title"><div><h2>Week view</h2><p className="muted">Next update can add create/edit and drag-and-drop. This page is currently read-only.</p></div></div><div className="schedule-grid">{days.map((day) => { const shifts = week.items.filter((item) => item.shift_date === day); return (<div className="schedule-day" key={day}><div className="schedule-day-head"><strong>{label(day)}</strong><span className="muted">{shifts.length} shift{shifts.length===1?"":"s"}</span></div><div className="schedule-stack">{shifts.map((shift)=>(<div className="shift-card" key={shift.id}><strong>{shift.employee_name || "Unassigned"}</strong><span>{shift.position}</span><span>{shift.start_time}–{shift.end_time}{shift.is_overnight ? " +1" : ""}</span><span>{numberText(shift.planned_paid_hours)} paid hrs · break {shift.break_minutes}m</span>{shift.notes ? <p className="muted">{shift.notes}</p> : null}</div>))}{shifts.length===0 ? <div className="empty-day">No shifts</div> : null}</div></div>); })}</div></section>
      </div>
    </Shell>
  );
}
