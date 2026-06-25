import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";
import { apiBaseUrl, numberText, peso } from "@/lib/api";

type PortalEmployee = {
  id: number;
  employee_code: string;
  name: string;
  department: string;
  position: string;
  status: string;
};

type PayrollItem = {
  id: number;
  period_start: string;
  period_end: string;
  payout_date: string;
  status: string;
  regular_hours?: number | null;
  approved_ot_hours?: number | null;
  night_diff_hours?: number | null;
  gross_pay: number;
  total_deductions: number;
  net_pay: number;
};

type ScheduleItem = {
  work_date: string;
  shift_start: string;
  shift_end: string;
  break_minutes: number;
  is_rest_day?: number | null;
  notes?: string | null;
  schedule_source?: string | null;
};

type AttendanceItem = {
  id: number;
  work_date: string;
  actual_in?: string | null;
  actual_out?: string | null;
  attendance_status?: string | null;
  is_absent?: number | null;
  absence_type?: string | null;
  approved_ot_hours?: number | null;
  ot_status?: string | null;
};

type LeaveBalance = {
  leave_type_name: string;
  credits: number;
  used: number;
  remaining: number;
  entitled: number;
  paid: number;
};

type LeaveRequest = {
  id: number;
  start_date: string;
  end_date: string;
  days: number;
  paid: number;
  status: string;
  reason?: string | null;
  leave_type_name?: string | null;
};

type HrRecord = {
  id: number;
  record_type: string;
  record_date: string;
  subject: string;
  severity: string;
  status: string;
  issued_by?: string | null;
};

type CashAdvance = {
  id: number;
  advance_date: string;
  amount: number;
  deduction_per_payroll: number;
  remaining_balance: number;
  status: string;
  reason?: string | null;
};

type PortalResponse = {
  ok: boolean;
  as_of: string;
  employee: PortalEmployee | null;
  summary: {
    visible_payslips: number;
    upcoming_shifts: number;
    recent_time_logs: number;
    leave_types: number;
    active_cash_advances: number;
    hr_records: number;
  };
  payroll: PayrollItem[];
  schedule: ScheduleItem[];
  attendance: AttendanceItem[];
  leave_balances: LeaveBalance[];
  leave_requests: LeaveRequest[];
  hr_records: HrRecord[];
  cash_advances: CashAdvance[];
  message?: string;
};

function hasHours(value: number | null | undefined) {
  return Number(value || 0) > 0;
}

function dateText(value: string | null | undefined) {
  if (!value) return "-";
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-PH", {
    month: "short",
    day: "numeric",
    weekday: "short",
  });
}

async function loadMyPortal(): Promise<PortalResponse> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) {
    return {
      ok: false,
      as_of: "",
      employee: null,
      summary: { visible_payslips: 0, upcoming_shifts: 0, recent_time_logs: 0, leave_types: 0, active_cash_advances: 0, hr_records: 0 },
      payroll: [],
      schedule: [],
      attendance: [],
      leave_balances: [],
      leave_requests: [],
      hr_records: [],
      cash_advances: [],
      message: "Not signed in.",
    };
  }
  const response = await fetch(`${apiBaseUrl()}/api/v1/me/portal`, {
    headers: {
      Authorization: `Bearer ${token}`,
      ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    },
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    return {
      ok: false,
      as_of: "",
      employee: null,
      summary: { visible_payslips: 0, upcoming_shifts: 0, recent_time_logs: 0, leave_types: 0, active_cash_advances: 0, hr_records: 0 },
      payroll: [],
      schedule: [],
      attendance: [],
      leave_balances: [],
      leave_requests: [],
      hr_records: [],
      cash_advances: [],
      message: data.detail || "No linked employee record.",
    };
  }
  return data as PortalResponse;
}

export default async function MyPortalPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "staff") {
    return <Shell allowedRoles={["staff"]}><div /></Shell>;
  }

  const portal = await loadMyPortal();
  const latestPay = portal.payroll[0];
  const nextShift = portal.schedule.find((item) => !item.is_rest_day);

  return (
    <Shell allowedRoles={["staff"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">My Portal</span>
            <h1>Hi, {session.display_name}.</h1>
            <p className="muted">{portal.employee ? `${portal.employee.department} · ${portal.employee.position || "Staff"}` : "Staff self-service"}</p>
          </div>
          <StatusBadge label={portal.ok ? "linked" : "needs setup"} tone={portal.ok ? "ok" : "warning"} />
        </header>

        {!portal.ok ? (
          <section className="card">
            <strong>Employee link needed</strong>
            <p className="muted">{portal.message || "Ask the owner to link your login to your employee record."}</p>
          </section>
        ) : null}

        <section className="grid cols-4">
          <div className="card"><strong>{portal.employee?.name || "Not linked"}</strong><p className="muted">{portal.employee?.employee_code || "Employee profile"}</p></div>
          <div className="card"><strong>{portal.summary.visible_payslips}</strong><p className="muted">Visible payslips</p></div>
          <div className="card"><strong>{portal.summary.upcoming_shifts}</strong><p className="muted">Upcoming shifts</p></div>
          <div className="card"><strong>{portal.summary.active_cash_advances}</strong><p className="muted">Active advances</p></div>
        </section>

        <section className="grid cols-2">
          <section className="card">
            <div className="panel-title"><div><h2>Next Shift</h2><p className="muted">Upcoming schedule from today forward.</p></div></div>
            {nextShift ? (
              <div className="action-list">
                <div className="action-item">
                  <strong>{dateText(nextShift.work_date)}</strong>
                  <p>{nextShift.shift_start} to {nextShift.shift_end}</p>
                  <p className="muted">Break {Number(nextShift.break_minutes || 0)} minutes{nextShift.notes ? ` · ${nextShift.notes}` : ""}</p>
                </div>
              </div>
            ) : <p className="muted">No upcoming shift posted yet.</p>}
          </section>

          <section className="card">
            <div className="panel-title"><div><h2>Latest Pay</h2><p className="muted">Approved, paid, or released payroll only.</p></div></div>
            {latestPay ? (
              <div className="action-list">
                <div className="action-item">
                  <strong>{latestPay.period_start} to {latestPay.period_end}</strong>
                  <p>{peso(latestPay.net_pay)} net pay</p>
                  <p className="muted">{numberText(latestPay.regular_hours)} regular hrs{hasHours(latestPay.approved_ot_hours) ? ` · ${numberText(latestPay.approved_ot_hours)} OT hrs` : ""}</p>
                </div>
              </div>
            ) : <p className="muted">No visible payslips yet.</p>}
          </section>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>Upcoming Schedule</h2><p className="muted">Next 14 days.</p></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Time</th><th>Break</th><th>Notes</th></tr></thead>
              <tbody>
                {portal.schedule.slice(0, 10).map((item, index) => (
                  <tr key={`${item.work_date}-${item.shift_start}-${index}`}>
                    <td>{dateText(item.work_date)}</td>
                    <td>{item.is_rest_day ? "Rest day" : `${item.shift_start} to ${item.shift_end}`}</td>
                    <td>{item.is_rest_day ? "-" : `${Number(item.break_minutes || 0)} min`}</td>
                    <td>{item.notes || item.schedule_source || "-"}</td>
                  </tr>
                ))}
                {!portal.schedule.length ? <tr><td colSpan={4}>No schedule posted for the next 14 days.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="grid cols-2">
          <section className="card">
            <div className="panel-title"><div><h2>Recent Attendance</h2><p className="muted">Recent time log status.</p></div></div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Date</th><th>In / Out</th><th>Status</th><th>OT</th></tr></thead>
                <tbody>
                  {portal.attendance.slice(0, 8).map((item) => (
                    <tr key={item.id}>
                      <td>{dateText(item.work_date)}</td>
                      <td>{item.is_absent ? item.absence_type || "Absent" : `${item.actual_in || "-"} / ${item.actual_out || "-"}`}</td>
                      <td>{item.attendance_status || "-"}</td>
                      <td>{hasHours(item.approved_ot_hours) ? `${numberText(item.approved_ot_hours)} hrs` : item.ot_status || "-"}</td>
                    </tr>
                  ))}
                  {!portal.attendance.length ? <tr><td colSpan={4}>No recent attendance logs.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card">
            <div className="panel-title"><div><h2>Leave Balances</h2><p className="muted">Current year entitlements.</p></div></div>
            <div className="action-list">
              {portal.leave_balances.map((item) => (
                <div className="action-item" key={item.leave_type_name}>
                  <strong>{item.leave_type_name}</strong>
                  <p>{numberText(item.remaining)} remaining / {numberText(item.credits)} credits</p>
                  <p className="muted">{numberText(item.used)} used · {item.paid ? "Paid" : "Unpaid"}</p>
                </div>
              ))}
              {!portal.leave_balances.length ? <p className="muted">No leave entitlement set yet.</p> : null}
            </div>
          </section>
        </section>

        <section className="grid cols-2">
          <section className="card">
            <div className="panel-title"><div><h2>Cash Advances</h2><p className="muted">Your recorded advance balances.</p></div></div>
            <div className="action-list">
              {portal.cash_advances.slice(0, 8).map((item) => (
                <div className="action-item" key={item.id}>
                  <strong>{peso(item.remaining_balance)} remaining</strong>
                  <p>{peso(item.amount)} advance · {item.status}</p>
                  <p className="muted">{item.advance_date}{item.reason ? ` · ${item.reason}` : ""}</p>
                </div>
              ))}
              {!portal.cash_advances.length ? <p className="muted">No cash advances recorded.</p> : null}
            </div>
          </section>

          <section className="card">
            <div className="panel-title"><div><h2>Formal Records</h2><p className="muted">Memos, infractions, and formal HR records linked to you.</p></div><Link className="primary-link" href="/hr">Open HR</Link></div>
            <div className="action-list">
              {portal.hr_records.slice(0, 8).map((item) => (
                <div className="action-item" key={item.id}>
                  <strong>{item.subject}</strong>
                  <p>{item.record_type} · {item.status}</p>
                  <p className="muted">{item.record_date} · {item.severity}{item.issued_by ? ` · ${item.issued_by}` : ""}</p>
                </div>
              ))}
              {!portal.hr_records.length ? <p className="muted">No formal records linked to you.</p> : null}
            </div>
          </section>
        </section>

        <section className="card">
          <div className="panel-title"><div><h2>My Payslips</h2><p className="muted">Approved or paid payroll only.</p></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Period</th><th>Payout</th><th>Status</th><th>Hours</th><th>Gross</th><th>Deductions</th><th>Net</th></tr></thead>
              <tbody>
                {portal.payroll.map((item) => (
                  <tr key={item.id}>
                    <td>{item.period_start} to {item.period_end}</td>
                    <td>{item.payout_date}</td>
                    <td>{item.status}</td>
                    <td>
                      <strong>{numberText(item.regular_hours)} regular hrs</strong>
                      {hasHours(item.approved_ot_hours) ? <><br /><span className="muted">{numberText(item.approved_ot_hours)} OT hrs</span></> : null}
                      {hasHours(item.night_diff_hours) ? <><br /><span className="muted">{numberText(item.night_diff_hours)} ND hrs</span></> : null}
                    </td>
                    <td>{peso(item.gross_pay)}</td>
                    <td>{peso(item.total_deductions)}</td>
                    <td><strong>{peso(item.net_pay)}</strong></td>
                  </tr>
                ))}
                {!portal.payroll.length ? <tr><td colSpan={7}>{portal.message || "No payslips yet."}</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
