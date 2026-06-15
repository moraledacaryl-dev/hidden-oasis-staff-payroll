from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from .db import execute, fetchall, fetchone, now_iso


def _iso(d: date | str | None) -> str:
    if d is None:
        return ""
    return d.isoformat() if isinstance(d, date) else str(d)


def _time_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%I:%M %p").lstrip("0")
        except Exception:
            pass
    return text


def _parse_time(value: Any, fallback: str = "08:00"):
    text = str(value or "").strip()
    for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except Exception:
            pass
    return datetime.strptime(fallback, "%H:%M").time()


def _status_badge(cell: dict[str, Any]) -> tuple[str, str]:
    schedule = cell.get("schedule")
    log = cell.get("log")
    if log and int(log.get("is_absent") or 0):
        return "Absent", "cell-bad"
    if log and str(log.get("absence_type") or "").strip():
        return str(log.get("absence_type")), "cell-leave"
    if schedule and not log:
        return "No log", "cell-warn"
    if log and not str(log.get("actual_out") or "").strip() and not int(log.get("is_absent") or 0):
        return "Missing out", "cell-warn"
    if log and str(log.get("attendance_status") or "").lower() in {"pending", "needs manager", "disputed"}:
        return str(log.get("attendance_status") or "Pending"), "cell-pending"
    if log and "late" in str(log.get("notes") or "").lower():
        return "Late", "cell-warn"
    if schedule or log:
        return "OK", "cell-ok"
    return "—", "cell-empty"


def _department_names(conn, include_all: bool = True) -> list[str]:
    rows = fetchall(conn, "SELECT name FROM departments WHERE active=1 ORDER BY name")
    names = [r["name"] for r in rows]
    return (["All"] if include_all else []) + names


def _employee_options(conn, department: str) -> dict[str, int]:
    if department and department != "All":
        rows = fetchall(
            conn,
            "SELECT id, employee_code, full_name, department FROM employees WHERE status NOT IN ('Inactive','Terminated') AND department=? ORDER BY full_name",
            (department,),
        )
    else:
        rows = fetchall(
            conn,
            "SELECT id, employee_code, full_name, department FROM employees WHERE status NOT IN ('Inactive','Terminated') ORDER BY department, full_name",
        )
    return {f"{r['full_name']} ({r['employee_code']}) • {r['department']}": int(r["id"]) for r in rows}


def _load_week(conn, start: date, end: date, department: str) -> tuple[list[dict[str, Any]], dict[tuple[int, str], dict[str, Any]]]:
    if department and department != "All":
        employees = fetchall(
            conn,
            "SELECT id, employee_code, full_name, department, position FROM employees WHERE status NOT IN ('Inactive','Terminated') AND department=? ORDER BY full_name",
            (department,),
        )
    else:
        employees = fetchall(
            conn,
            "SELECT id, employee_code, full_name, department, position FROM employees WHERE status NOT IN ('Inactive','Terminated') ORDER BY department, full_name",
        )
    emp_ids = [int(e["id"]) for e in employees]
    grid: dict[tuple[int, str], dict[str, Any]] = {}
    if not emp_ids:
        return employees, grid

    placeholders = ",".join(["?"] * len(emp_ids))
    sched_rows = fetchall(
        conn,
        f"""
        SELECT * FROM schedules
        WHERE employee_id IN ({placeholders}) AND work_date BETWEEN ? AND ?
        ORDER BY work_date, shift_start
        """,
        (*emp_ids, _iso(start), _iso(end)),
    )
    log_rows = fetchall(
        conn,
        f"""
        SELECT * FROM time_logs
        WHERE employee_id IN ({placeholders}) AND work_date BETWEEN ? AND ?
        ORDER BY work_date, actual_in
        """,
        (*emp_ids, _iso(start), _iso(end)),
    )

    for s in sched_rows:
        key = (int(s["employee_id"]), str(s["work_date"]))
        grid.setdefault(key, {})["schedule"] = s
    for l in log_rows:
        key = (int(l["employee_id"]), str(l["work_date"]))
        grid.setdefault(key, {})["log"] = l
    return employees, grid


def _cell_html(day: date, cell: dict[str, Any]) -> str:
    schedule = cell.get("schedule")
    log = cell.get("log")
    label, cls = _status_badge(cell)
    sched_text = ""
    if schedule:
        if int(schedule.get("is_rest_day") or 0):
            sched_text = "Rest day"
        else:
            sched_text = f"{_time_text(schedule.get('shift_start'))}–{_time_text(schedule.get('shift_end'))}"
    actual_text = ""
    if log:
        if int(log.get("is_absent") or 0):
            actual_text = "Absent"
        else:
            actual_text = f"{_time_text(log.get('actual_in'))}–{_time_text(log.get('actual_out'))}"
    if not sched_text and not actual_text:
        return f"<div class='cal-cell cell-empty'><div class='daynum'>{day.day}</div><div class='status'>—</div></div>"
    return (
        f"<div class='cal-cell {cls}'>"
        f"<div class='daynum'>{day.strftime('%a %d')}</div>"
        f"<div class='status'>{label}</div>"
        f"<div><b>Sched</b> {sched_text or '—'}</div>"
        f"<div><b>Actual</b> {actual_text or '—'}</div>"
        f"</div>"
    )


def render_calendar_review(conn, current_user: str, audit_func=None) -> None:
    st.title("Calendar Review")
    st.caption("Sling-style weekly review: employee rows, day columns, schedule + actual logs in one place. Use the editor below for corrections before payroll.")

    st.markdown(
        """
        <style>
        .calendar-wrap { overflow-x: auto; border: 1px solid #e7e2d8; border-radius: 18px; }
        table.calendar { border-collapse: separate; border-spacing: 0; min-width: 1120px; width: 100%; font-size: 0.82rem; }
        .calendar th { position: sticky; top: 0; background: #f8f5ef; z-index: 2; padding: 10px; border-bottom: 1px solid #e7e2d8; text-align: left; }
        .calendar td { vertical-align: top; padding: 7px; border-bottom: 1px solid #eee8de; border-right: 1px solid #eee8de; }
        .emp-col { position: sticky; left: 0; z-index: 1; background: #fffdf8; min-width: 190px; max-width: 230px; font-weight: 650; }
        .emp-meta { color: #7b756c; font-size: 0.75rem; font-weight: 400; margin-top: 3px; }
        .cal-cell { min-height: 92px; border-radius: 14px; padding: 8px; line-height: 1.35; border: 1px solid #ddd4c8; background: #fff; }
        .daynum { font-weight: 750; margin-bottom: 4px; }
        .status { display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 0.72rem; margin-bottom: 6px; background: rgba(255,255,255,.7); }
        .cell-ok { background: #eef8ef; border-color: #bedfbe; }
        .cell-warn { background: #fff6dc; border-color: #e8ca78; }
        .cell-bad { background: #ffe8e5; border-color: #e8a39b; }
        .cell-pending { background: #eaf1ff; border-color: #aec5ef; }
        .cell-leave { background: #f2eafd; border-color: #cdb7ef; }
        .cell-empty { background: #f7f4ee; color: #9a9288; border-color: #ece6dc; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    week_start = c1.date_input("Week start", value=date.today() - timedelta(days=date.today().weekday()))
    week_start = week_start - timedelta(days=week_start.weekday())
    week_end = week_start + timedelta(days=6)
    departments = _department_names(conn)
    department = c2.selectbox("Department", departments)
    view_mode = c3.selectbox("View", ["All", "Exceptions only", "Missing logs", "Pending review"])
    if c4.button("Refresh"):
        st.rerun()

    employees, grid = _load_week(conn, week_start, week_end, department)
    days = [week_start + timedelta(days=i) for i in range(7)]

    def include_emp(emp: dict[str, Any]) -> bool:
        if view_mode == "All":
            return True
        for d in days:
            cell = grid.get((int(emp["id"]), _iso(d)), {})
            label, _cls = _status_badge(cell)
            if view_mode == "Exceptions only" and label not in {"OK", "—"}:
                return True
            if view_mode == "Missing logs" and label in {"No log", "Missing out"}:
                return True
            if view_mode == "Pending review" and label in {"Pending", "Needs Manager", "Disputed"}:
                return True
        return False

    employees = [e for e in employees if include_emp(e)]

    html = ["<div class='calendar-wrap'><table class='calendar'>"]
    html.append("<tr><th class='emp-col'>Employee</th>" + "".join([f"<th>{d.strftime('%a %b %d')}</th>" for d in days]) + "</tr>")
    for emp in employees:
        html.append("<tr>")
        html.append(f"<td class='emp-col'>{emp['full_name']}<div class='emp-meta'>{emp.get('employee_code','')} • {emp.get('department','')} • {emp.get('position','')}</div></td>")
        for d in days:
            html.append(f"<td>{_cell_html(d, grid.get((int(emp['id']), _iso(d)), {}))}</td>")
        html.append("</tr>")
    html.append("</table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Edit selected employee/date")
    emp_options = _employee_options(conn, department)
    if not emp_options:
        st.info("No active employees for this filter.")
        return

    e1, e2 = st.columns([2, 1])
    emp_label = e1.selectbox("Employee", list(emp_options.keys()))
    selected_date = e2.date_input("Date to edit", value=week_start, min_value=week_start, max_value=week_end)
    employee_id = emp_options[emp_label]
    selected_iso = _iso(selected_date)
    schedule = fetchone(conn, "SELECT * FROM schedules WHERE employee_id=? AND work_date=? ORDER BY shift_start LIMIT 1", (employee_id, selected_iso))
    log = fetchone(conn, "SELECT * FROM time_logs WHERE employee_id=? AND work_date=? ORDER BY actual_in LIMIT 1", (employee_id, selected_iso))
    emp = fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,)) or {}

    left, right = st.columns(2)
    with left:
        st.markdown("### Schedule")
        with st.form("calendar_schedule_form"):
            s1, s2, s3 = st.columns(3)
            shift_start = s1.time_input("Shift start", value=_parse_time((schedule or {}).get("shift_start"), "08:00"))
            shift_end = s2.time_input("Shift end", value=_parse_time((schedule or {}).get("shift_end"), "17:00"))
            break_minutes = s3.number_input("Break minutes", min_value=0, value=int((schedule or {}).get("break_minutes") or (0 if str(emp.get('department','')).lower() == 'security' else 60)), step=15)
            dept_options = [""] + [d for d in _department_names(conn, include_all=False)]
            default_dept = (schedule or {}).get("department") or emp.get("department") or ""
            dept_idx = dept_options.index(default_dept) if default_dept in dept_options else 0
            sched_dept = st.selectbox("Department / Area", dept_options, index=dept_idx, key="cal_sched_dept")
            rest_day = st.checkbox("Rest day", value=bool((schedule or {}).get("is_rest_day") or 0))
            sched_notes = st.text_area("Schedule notes", value=str((schedule or {}).get("notes") or ""), key="cal_sched_notes")
            save_sched = st.form_submit_button("Save schedule", type="primary")
            if save_sched:
                execute(
                    conn,
                    """
                    INSERT OR REPLACE INTO schedules(employee_id, work_date, shift_start, shift_end, break_minutes, department, location, is_rest_day, notes)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (employee_id, selected_iso, shift_start.strftime("%H:%M"), shift_end.strftime("%H:%M"), int(break_minutes), sched_dept, sched_dept, int(rest_day), sched_notes),
                )
                if audit_func:
                    audit_func(current_user, "Calendar saved schedule", "schedules", employee_id, f"{emp_label} {selected_iso}")
                st.success("Schedule saved.")
                st.rerun()

    with right:
        st.markdown("### Actual log")
        with st.form("calendar_log_form"):
            l1, l2, l3 = st.columns(3)
            actual_in = l1.time_input("Actual in", value=_parse_time((log or {}).get("actual_in"), "08:00"))
            actual_out = l2.time_input("Actual out", value=_parse_time((log or {}).get("actual_out"), "17:00"))
            missing_out = l3.checkbox("No time out yet", value=not bool((log or {}).get("actual_out")))
            absent = st.checkbox("Mark absent", value=bool((log or {}).get("is_absent") or 0))
            absence_type = st.selectbox(
                "Absence / leave type",
                ["", "Absent", "Service Incentive Leave", "Sick Leave", "Bereavement Leave", "Unpaid Leave", "AWOL", "Suspension"],
                index=0,
            )
            a1, a2, a3 = st.columns(3)
            attendance_status = a1.selectbox("Attendance status", ["Pending", "Reviewed", "Needs Manager", "Disputed"], index=["Pending", "Reviewed", "Needs Manager", "Disputed"].index((log or {}).get("attendance_status") if (log or {}).get("attendance_status") in ["Pending", "Reviewed", "Needs Manager", "Disputed"] else "Pending"))
            ot_status = a2.selectbox("OT status", ["None", "Pending", "Approved", "Rejected"], index=["None", "Pending", "Approved", "Rejected"].index((log or {}).get("ot_status") if (log or {}).get("ot_status") in ["None", "Pending", "Approved", "Rejected"] else "None"))
            approved_ot = a3.number_input("Approved OT hours", min_value=0.0, value=float((log or {}).get("approved_ot_hours") or 0), step=0.25)
            notes = st.text_area("Log notes", value=str((log or {}).get("notes") or ""), key="cal_log_notes")
            save_log = st.form_submit_button("Save actual log", type="primary")
            if save_log:
                out_text = "" if missing_out or absent else actual_out.strftime("%H:%M")
                in_text = "" if absent else actual_in.strftime("%H:%M")
                execute(
                    conn,
                    """
                    INSERT OR REPLACE INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type,
                        is_absent, absence_type, approved_ot_hours, ot_status, ot_reason_category, ot_reason_note,
                        attendance_status, notes, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (employee_id, selected_iso, in_text, out_text, "calendar", "Calendar Review", int(absent), absence_type, float(approved_ot), ot_status, "Calendar correction", "", attendance_status, notes, now_iso(), now_iso()),
                )
                if audit_func:
                    audit_func(current_user, "Calendar saved time log", "time_logs", employee_id, f"{emp_label} {selected_iso}")
                st.success("Actual log saved.")
                st.rerun()

    st.markdown("### Quick actions")
    q1, q2, q3, q4, q5 = st.columns(5)
    if q1.button("Mark reviewed"):
        if log:
            execute(conn, "UPDATE time_logs SET attendance_status='Reviewed', reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?", (current_user, now_iso(), now_iso(), log["id"]))
            st.success("Marked reviewed.")
            st.rerun()
        else:
            st.warning("No time log to review yet.")
    if q2.button("Mark absent"):
        execute(
            conn,
            """
            INSERT OR REPLACE INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type,
                is_absent, absence_type, approved_ot_hours, ot_status, attendance_status, notes, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (employee_id, selected_iso, "", "", "calendar", "Calendar Review", 1, "Absent", 0, "None", "Reviewed", "Marked absent from calendar", now_iso(), now_iso()),
        )
        st.success("Marked absent.")
        st.rerun()
    if q3.button("SIL"):
        _create_leave_and_absence(conn, employee_id, selected_iso, "Service Incentive Leave", current_user)
        st.success("Marked SIL.")
        st.rerun()
    if q4.button("Sick leave"):
        _create_leave_and_absence(conn, employee_id, selected_iso, "Sick Leave", current_user)
        st.success("Marked sick leave.")
        st.rerun()
    if q5.button("Copy sched → actual"):
        if not schedule:
            st.warning("No schedule to copy.")
        else:
            execute(
                conn,
                """
                INSERT OR REPLACE INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type,
                    is_absent, approved_ot_hours, ot_status, attendance_status, notes, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (employee_id, selected_iso, schedule["shift_start"], schedule["shift_end"], "calendar", "Copied from schedule", 0, 0, "None", "Reviewed", "Copied scheduled shift to actual log", now_iso(), now_iso()),
            )
            st.success("Copied schedule into actual log.")
            st.rerun()


def _create_leave_and_absence(conn, employee_id: int, day: str, leave_type_name: str, actor: str) -> None:
    lt = fetchone(conn, "SELECT id FROM leave_types WHERE lower(name)=lower(?)", (leave_type_name,))
    if not lt:
        execute(conn, "INSERT INTO leave_types(name, default_credits, paid, statutory, requires_approval, active, notes) VALUES(?,?,?,?,?,?,?)", (leave_type_name, 0, 1, 0, 1, 1, "Created from Calendar Review"))
        lt = fetchone(conn, "SELECT id FROM leave_types WHERE lower(name)=lower(?)", (leave_type_name,))
    execute(
        conn,
        "INSERT INTO leave_requests(employee_id, leave_type_id, start_date, end_date, days, paid, status, reason, reviewed_by, reviewed_at, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (employee_id, int(lt["id"]), day, day, 1, 1, "Approved", "Calendar Review quick action", actor, now_iso(), now_iso()),
    )
    execute(
        conn,
        """
        INSERT OR REPLACE INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type,
            is_absent, absence_type, approved_ot_hours, ot_status, attendance_status, notes, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (employee_id, day, "", "", "calendar", "Calendar Review", 1, leave_type_name, 0, "None", "Reviewed", f"Marked {leave_type_name} from calendar", now_iso(), now_iso()),
    )
