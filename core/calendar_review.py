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


def _status_badge(cell: dict[str, Any], holiday: dict[str, Any] | None = None) -> tuple[str, str, str]:
    schedule = cell.get("schedule")
    log = cell.get("log")
    if log and int(log.get("is_absent") or 0):
        absence_type = str(log.get("absence_type") or "Absent")
        return absence_type, "🔴", "bad"
    if log and str(log.get("absence_type") or "").strip():
        return str(log.get("absence_type")), "🟣", "leave"
    if schedule and int(schedule.get("is_rest_day") or 0):
        return "Rest", "⚪", "empty"
    if schedule and not log:
        return "No log", "🟡", "warn"
    if log and not str(log.get("actual_out") or "").strip() and not int(log.get("is_absent") or 0):
        return "Missing out", "🟡", "warn"
    if log and str(log.get("attendance_status") or "").lower() in {"pending", "needs manager", "disputed"}:
        return str(log.get("attendance_status") or "Pending"), "🔵", "pending"
    if log and "late" in str(log.get("notes") or "").lower():
        return "Late", "🟡", "warn"
    if holiday and (schedule or log):
        return f"{holiday.get('holiday_type', 'Holiday')}", "🎌", "holiday"
    if schedule or log:
        return "OK", "🟢", "ok"
    if holiday:
        return f"{holiday.get('holiday_type', 'Holiday')}", "🎌", "holiday"
    return "—", "⚪", "empty"


def _department_names(conn, include_all: bool = True) -> list[str]:
    rows = fetchall(conn, "SELECT name FROM departments WHERE active=1 ORDER BY name")
    names = [r["name"] for r in rows]
    return (["All"] if include_all else []) + names


def _employee_rows(conn, department: str) -> list[dict[str, Any]]:
    if department and department != "All":
        return fetchall(
            conn,
            """
            SELECT id, employee_code, full_name, department, position
            FROM employees
            WHERE status NOT IN ('Inactive','Terminated') AND department=?
            ORDER BY full_name
            """,
            (department,),
        )
    return fetchall(
        conn,
        """
        SELECT id, employee_code, full_name, department, position
        FROM employees
        WHERE status NOT IN ('Inactive','Terminated')
        ORDER BY department, full_name
        """,
    )


def _employee_options(conn, department: str) -> dict[str, int]:
    return {f"{r['full_name']} ({r['employee_code']}) • {r['department']}": int(r["id"]) for r in _employee_rows(conn, department)}


def _load_week(conn, start: date, end: date, department: str) -> tuple[list[dict[str, Any]], dict[tuple[int, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    employees = _employee_rows(conn, department)
    emp_ids = [int(e["id"]) for e in employees]
    grid: dict[tuple[int, str], dict[str, Any]] = {}
    holidays = {
        str(h["holiday_date"]): h
        for h in fetchall(conn, "SELECT * FROM holidays WHERE active=1 AND holiday_date BETWEEN ? AND ?", (_iso(start), _iso(end)))
    }
    if not emp_ids:
        return employees, grid, holidays

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
    return employees, grid, holidays


def _cell_label(day: date, cell: dict[str, Any], holiday: dict[str, Any] | None) -> str:
    schedule = cell.get("schedule")
    log = cell.get("log")
    label, icon, _kind = _status_badge(cell, holiday)
    lines = [f"{icon} {day.strftime('%a %d')}", label]
    if holiday:
        lines.append(f"Holiday: {holiday['name']}")
    if schedule:
        if int(schedule.get("is_rest_day") or 0):
            lines.append("Sched: Rest day")
        else:
            lines.append(f"S: {_time_text(schedule.get('shift_start'))}-{_time_text(schedule.get('shift_end'))}")
    else:
        lines.append("S: —")
    if log:
        if int(log.get("is_absent") or 0):
            lines.append(f"A: {log.get('absence_type') or 'Absent'}")
        else:
            lines.append(f"A: {_time_text(log.get('actual_in'))}-{_time_text(log.get('actual_out')) or '—'}")
    else:
        lines.append("A: —")
    return "\n".join(lines)


def _save_schedule(conn, employee_id: int, work_date: str, shift_start: str, shift_end: str, break_minutes: int, department: str, rest_day: bool, notes: str, schedule_id: int | None = None) -> None:
    if schedule_id:
        execute(
            conn,
            """
            UPDATE schedules
            SET shift_start=?, shift_end=?, break_minutes=?, department=?, location=?, is_rest_day=?, notes=?
            WHERE id=?
            """,
            (shift_start, shift_end, int(break_minutes), department, department, int(rest_day), notes, schedule_id),
        )
        return
    execute(
        conn,
        """
        INSERT OR REPLACE INTO schedules(employee_id, work_date, shift_start, shift_end, break_minutes, department, location, is_rest_day, notes)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (employee_id, work_date, shift_start, shift_end, int(break_minutes), department, department, int(rest_day), notes),
    )


def _save_time_log(conn, employee_id: int, work_date: str, actual_in: str, actual_out: str, absent: bool, absence_type: str, approved_ot: float, ot_status: str, ot_reason_category: str, ot_reason_note: str, attendance_status: str, notes: str, log_id: int | None = None) -> None:
    if log_id:
        execute(
            conn,
            """
            UPDATE time_logs
            SET actual_in=?, actual_out=?, source='calendar', verification_type='Calendar Review',
                is_absent=?, absence_type=?, approved_ot_hours=?, ot_status=?, ot_reason_category=?, ot_reason_note=?,
                attendance_status=?, notes=?, updated_at=?
            WHERE id=?
            """,
            (actual_in, actual_out, int(absent), absence_type, float(approved_ot), ot_status, ot_reason_category, ot_reason_note, attendance_status, notes, now_iso(), log_id),
        )
        return
    execute(
        conn,
        """
        INSERT INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type,
            is_absent, absence_type, approved_ot_hours, ot_status, ot_reason_category, ot_reason_note,
            attendance_status, notes, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (employee_id, work_date, actual_in, actual_out, "calendar", "Calendar Review", int(absent), absence_type, float(approved_ot), ot_status, ot_reason_category, ot_reason_note, attendance_status, notes, now_iso(), now_iso()),
    )


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
    existing = fetchone(conn, "SELECT id FROM time_logs WHERE employee_id=? AND work_date=? ORDER BY id DESC LIMIT 1", (employee_id, day))
    _save_time_log(conn, employee_id, day, "", "", True, leave_type_name, 0, "None", "", "", "Reviewed", f"Marked {leave_type_name} from calendar", int(existing["id"]) if existing else None)


def _upsert_holiday(conn, holiday_date: str, name: str, holiday_type: str, notes: str) -> None:
    execute(
        conn,
        """
        INSERT INTO holidays(holiday_date, name, holiday_type, active, notes, created_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(holiday_date) DO UPDATE SET name=excluded.name, holiday_type=excluded.holiday_type, active=excluded.active, notes=excluded.notes
        """,
        (holiday_date, name, holiday_type, 1, notes, now_iso()),
    )


def _delete_schedule(conn, schedule_id: int | None) -> None:
    if schedule_id:
        execute(conn, "DELETE FROM schedules WHERE id=?", (schedule_id,))


def _clear_log(conn, log_id: int | None) -> None:
    if log_id:
        execute(conn, "DELETE FROM time_logs WHERE id=?", (log_id,))


def _copy_schedule_to_actual(conn, employee_id: int, selected_iso: str, schedule: dict[str, Any] | None, log: dict[str, Any] | None) -> None:
    if not schedule:
        return
    _save_time_log(
        conn,
        employee_id,
        selected_iso,
        str(schedule["shift_start"]),
        str(schedule["shift_end"]),
        False,
        "",
        0,
        "None",
        "Copied from schedule",
        "",
        "Reviewed",
        "Copied scheduled shift to actual log",
        int(log["id"]) if log else None,
    )


def _render_cell_editor(conn, current_user: str, employee_id: int, selected_date: date, audit_func=None) -> None:
    selected_iso = _iso(selected_date)
    emp = fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,)) or {}
    schedule = fetchone(conn, "SELECT * FROM schedules WHERE employee_id=? AND work_date=? ORDER BY shift_start LIMIT 1", (employee_id, selected_iso))
    log = fetchone(conn, "SELECT * FROM time_logs WHERE employee_id=? AND work_date=? ORDER BY id DESC LIMIT 1", (employee_id, selected_iso))
    holiday = fetchone(conn, "SELECT * FROM holidays WHERE holiday_date=? AND active=1", (selected_iso,))

    st.markdown(f"### {emp.get('full_name', 'Employee')} — {selected_date.strftime('%a, %b %d, %Y')}")
    if holiday:
        st.info(f"Holiday on this date: {holiday['name']} ({holiday['holiday_type']})")

    tab_sched, tab_log, tab_leave, tab_holiday, tab_quick = st.tabs(["Schedule", "Actual / OT", "Leave / Absence", "Holiday", "Quick Actions"])

    with tab_sched:
        with st.form(f"schedule_form_{employee_id}_{selected_iso}"):
            s1, s2, s3 = st.columns(3)
            shift_start = s1.time_input("Shift start", value=_parse_time((schedule or {}).get("shift_start"), "08:00"), key=f"sched_start_{employee_id}_{selected_iso}")
            shift_end = s2.time_input("Shift end", value=_parse_time((schedule or {}).get("shift_end"), "17:00"), key=f"sched_end_{employee_id}_{selected_iso}")
            default_break = int((schedule or {}).get("break_minutes") or (0 if str(emp.get("department", "")).lower() == "security" else 60))
            break_minutes = s3.number_input("Break minutes", min_value=0, value=default_break, step=15, key=f"sched_break_{employee_id}_{selected_iso}")
            dept_options = [""] + _department_names(conn, include_all=False)
            default_dept = (schedule or {}).get("department") or emp.get("department") or ""
            dept_idx = dept_options.index(default_dept) if default_dept in dept_options else 0
            sched_dept = st.selectbox("Department / Area", dept_options, index=dept_idx, key=f"sched_dept_{employee_id}_{selected_iso}")
            rest_day = st.checkbox("Rest day", value=bool((schedule or {}).get("is_rest_day") or 0), key=f"rest_{employee_id}_{selected_iso}")
            sched_notes = st.text_area("Schedule notes", value=str((schedule or {}).get("notes") or ""), key=f"sched_notes_{employee_id}_{selected_iso}")
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Save schedule", type="primary"):
                _save_schedule(conn, employee_id, selected_iso, shift_start.strftime("%H:%M"), shift_end.strftime("%H:%M"), int(break_minutes), sched_dept, bool(rest_day), sched_notes, int(schedule["id"]) if schedule else None)
                if audit_func:
                    audit_func(current_user, "Calendar saved schedule", "schedules", employee_id, f"{emp.get('full_name')} {selected_iso}")
                st.success("Schedule saved.")
                st.rerun()
            if c2.form_submit_button("Delete schedule"):
                _delete_schedule(conn, int(schedule["id"]) if schedule else None)
                st.success("Schedule deleted.")
                st.rerun()

    with tab_log:
        with st.form(f"log_form_{employee_id}_{selected_iso}"):
            l1, l2, l3 = st.columns(3)
            actual_in = l1.time_input("Actual in", value=_parse_time((log or {}).get("actual_in"), "08:00"), key=f"actual_in_{employee_id}_{selected_iso}")
            actual_out = l2.time_input("Actual out", value=_parse_time((log or {}).get("actual_out"), "17:00"), key=f"actual_out_{employee_id}_{selected_iso}")
            missing_out = l3.checkbox("No time out yet", value=not bool((log or {}).get("actual_out")), key=f"missing_out_{employee_id}_{selected_iso}")
            absent = st.checkbox("Mark absent", value=bool((log or {}).get("is_absent") or 0), key=f"absent_{employee_id}_{selected_iso}")
            absence_options = ["", "Absent", "Service Incentive Leave", "Sick Leave", "Bereavement Leave", "Unpaid Leave", "AWOL", "Suspension"]
            existing_absence = str((log or {}).get("absence_type") or "")
            absence_idx = absence_options.index(existing_absence) if existing_absence in absence_options else 0
            absence_type = st.selectbox("Absence / leave type", absence_options, index=absence_idx, key=f"absence_type_{employee_id}_{selected_iso}")
            a1, a2, a3 = st.columns(3)
            attendance_options = ["Pending", "Reviewed", "Needs Manager", "Disputed"]
            existing_att = (log or {}).get("attendance_status") if (log or {}).get("attendance_status") in attendance_options else "Pending"
            attendance_status = a1.selectbox("Attendance status", attendance_options, index=attendance_options.index(existing_att), key=f"att_status_{employee_id}_{selected_iso}")
            ot_options = ["None", "Pending", "Approved", "Rejected"]
            existing_ot = (log or {}).get("ot_status") if (log or {}).get("ot_status") in ot_options else "None"
            ot_status = a2.selectbox("OT status", ot_options, index=ot_options.index(existing_ot), key=f"ot_status_{employee_id}_{selected_iso}")
            approved_ot = a3.number_input("Approved OT hours", min_value=0.0, value=float((log or {}).get("approved_ot_hours") or 0), step=0.25, key=f"approved_ot_{employee_id}_{selected_iso}")
            ot_reason_category = st.selectbox("OT reason category", ["", "High guest volume", "Event", "Late checkout", "Emergency coverage", "Manager approved", "Other"], key=f"ot_cat_{employee_id}_{selected_iso}")
            ot_reason_note = st.text_area("OT reason note", value=str((log or {}).get("ot_reason_note") or ""), key=f"ot_note_{employee_id}_{selected_iso}")
            notes = st.text_area("Log notes", value=str((log or {}).get("notes") or ""), key=f"log_notes_{employee_id}_{selected_iso}")
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Save actual / OT", type="primary"):
                out_text = "" if missing_out or absent else actual_out.strftime("%H:%M")
                in_text = "" if absent else actual_in.strftime("%H:%M")
                _save_time_log(conn, employee_id, selected_iso, in_text, out_text, bool(absent), absence_type, float(approved_ot), ot_status, ot_reason_category, ot_reason_note, attendance_status, notes, int(log["id"]) if log else None)
                if audit_func:
                    audit_func(current_user, "Calendar saved time log", "time_logs", employee_id, f"{emp.get('full_name')} {selected_iso}")
                st.success("Actual log saved.")
                st.rerun()
            if c2.form_submit_button("Clear actual log"):
                _clear_log(conn, int(log["id"]) if log else None)
                st.success("Actual log cleared.")
                st.rerun()

    with tab_leave:
        leave_types = fetchall(conn, "SELECT name FROM leave_types WHERE active=1 ORDER BY name")
        leave_names = [r["name"] for r in leave_types] or ["Service Incentive Leave", "Sick Leave", "Bereavement Leave", "Unpaid Leave"]
        with st.form(f"leave_form_{employee_id}_{selected_iso}"):
            leave_name = st.selectbox("Leave type", leave_names, key=f"leave_name_{employee_id}_{selected_iso}")
            paid = st.checkbox("Paid leave", value=True, key=f"leave_paid_{employee_id}_{selected_iso}")
            status = st.selectbox("Leave status", ["Pending", "Approved", "Rejected"], index=1, key=f"leave_status_{employee_id}_{selected_iso}")
            reason = st.text_area("Reason", value="Calendar Review entry", key=f"leave_reason_{employee_id}_{selected_iso}")
            if st.form_submit_button("Save leave / absence", type="primary"):
                lt = fetchone(conn, "SELECT id FROM leave_types WHERE lower(name)=lower(?)", (leave_name,))
                if not lt:
                    execute(conn, "INSERT INTO leave_types(name, default_credits, paid, statutory, requires_approval, active, notes) VALUES(?,?,?,?,?,?,?)", (leave_name, 0, int(paid), 0, 1, 1, "Created from Calendar Review"))
                    lt = fetchone(conn, "SELECT id FROM leave_types WHERE lower(name)=lower(?)", (leave_name,))
                execute(conn, "INSERT INTO leave_requests(employee_id, leave_type_id, start_date, end_date, days, paid, status, reason, reviewed_by, reviewed_at, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (employee_id, int(lt["id"]), selected_iso, selected_iso, 1, int(paid), status, reason, current_user if status == "Approved" else "", now_iso() if status == "Approved" else "", now_iso()))
                _save_time_log(conn, employee_id, selected_iso, "", "", True, leave_name, 0, "None", "", "", "Reviewed" if status == "Approved" else "Pending", f"Marked {leave_name} from Calendar Review", int(log["id"]) if log else None)
                st.success("Leave / absence saved.")
                st.rerun()

    with tab_holiday:
        st.caption("Holiday is date-level. Once saved here, the holiday applies to everyone for this date and can be used by payroll holiday logic.")
        with st.form(f"holiday_form_{selected_iso}"):
            hname = st.text_input("Holiday name", value=str((holiday or {}).get("name") or ""), key=f"holiday_name_{selected_iso}")
            htype_options = ["Regular", "Special"]
            existing_htype = (holiday or {}).get("holiday_type") if (holiday or {}).get("holiday_type") in htype_options else "Regular"
            htype = st.selectbox("Holiday type", htype_options, index=htype_options.index(existing_htype), key=f"holiday_type_{selected_iso}")
            hnotes = st.text_area("Holiday notes", value=str((holiday or {}).get("notes") or ""), key=f"holiday_notes_{selected_iso}")
            if st.form_submit_button("Save holiday for this date", type="primary"):
                if not hname.strip():
                    st.error("Holiday name is required.")
                else:
                    _upsert_holiday(conn, selected_iso, hname.strip(), htype, hnotes)
                    if audit_func:
                        audit_func(current_user, "Calendar saved holiday", "holidays", None, f"{selected_iso} {hname.strip()} {htype}")
                    st.success("Holiday saved for this date.")
                    st.rerun()

    with tab_quick:
        q1, q2, q3, q4 = st.columns(4)
        if q1.button("Mark reviewed", key=f"q_review_{employee_id}_{selected_iso}"):
            if log:
                execute(conn, "UPDATE time_logs SET attendance_status='Reviewed', reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?", (current_user, now_iso(), now_iso(), int(log["id"])))
            else:
                _save_time_log(conn, employee_id, selected_iso, "", "", False, "", 0, "None", "", "", "Reviewed", "Reviewed empty day from calendar", None)
            st.success("Marked reviewed.")
            st.rerun()
        if q2.button("Mark rest day", key=f"q_rest_{employee_id}_{selected_iso}"):
            _save_schedule(conn, employee_id, selected_iso, "00:00", "00:00", 0, str(emp.get("department") or ""), True, "Marked rest day from calendar", int(schedule["id"]) if schedule else None)
            st.success("Marked rest day.")
            st.rerun()
        if q3.button("Copy schedule → actual", key=f"q_copy_{employee_id}_{selected_iso}"):
            if not schedule:
                st.warning("No schedule to copy.")
            else:
                _copy_schedule_to_actual(conn, employee_id, selected_iso, schedule, log)
                st.success("Copied schedule to actual.")
                st.rerun()
        if q4.button("Approve detected OT", key=f"q_ot_{employee_id}_{selected_iso}"):
            if not log:
                st.warning("No time log yet.")
            else:
                detected = float(log.get("detected_ot_hours") or log.get("approved_ot_hours") or 0)
                execute(conn, "UPDATE time_logs SET approved_ot_hours=?, ot_status='Approved', attendance_status='Reviewed', reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?", (detected, current_user, now_iso(), now_iso(), int(log["id"])))
                st.success("Detected OT approved.")
                st.rerun()
        q5, q6, q7, q8 = st.columns(4)
        if q5.button("SIL", key=f"q_sil_{employee_id}_{selected_iso}"):
            _create_leave_and_absence(conn, employee_id, selected_iso, "Service Incentive Leave", current_user)
            st.success("Marked SIL.")
            st.rerun()
        if q6.button("Sick leave", key=f"q_sl_{employee_id}_{selected_iso}"):
            _create_leave_and_absence(conn, employee_id, selected_iso, "Sick Leave", current_user)
            st.success("Marked sick leave.")
            st.rerun()
        if q7.button("Bereavement", key=f"q_bl_{employee_id}_{selected_iso}"):
            _create_leave_and_absence(conn, employee_id, selected_iso, "Bereavement Leave", current_user)
            st.success("Marked bereavement leave.")
            st.rerun()
        if q8.button("Absent", key=f"q_abs_{employee_id}_{selected_iso}"):
            _save_time_log(conn, employee_id, selected_iso, "", "", True, "Absent", 0, "None", "", "", "Reviewed", "Marked absent from Calendar Review", int(log["id"]) if log else None)
            st.success("Marked absent.")
            st.rerun()


def _open_editor(conn, current_user: str, audit_func=None) -> None:
    payload = st.session_state.get("calendar_cell_to_edit")
    if not payload:
        return
    employee_id = int(payload["employee_id"])
    selected_date = datetime.strptime(payload["date"], "%Y-%m-%d").date()

    if hasattr(st, "dialog"):
        @st.dialog("Edit schedule / actual / leave / holiday / OT", width="large")
        def popup() -> None:
            _render_cell_editor(conn, current_user, employee_id, selected_date, audit_func)
            if st.button("Close", key=f"close_popup_{employee_id}_{payload['date']}"):
                st.session_state.pop("calendar_cell_to_edit", None)
                st.rerun()
        popup()
    else:
        st.warning("This Streamlit version does not support modal popups yet, so the cell editor is shown below the calendar.")
        _render_cell_editor(conn, current_user, employee_id, selected_date, audit_func)


def render_calendar_review(conn, current_user: str, audit_func=None) -> None:
    st.title("Calendar Review")
    st.caption("Sling-style weekly review: click any employee/day cell to edit schedule, actual log, rest day, leave, holiday, and OT details.")

    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    week_start = c1.date_input("Week start", value=date.today() - timedelta(days=date.today().weekday()))
    week_start = week_start - timedelta(days=week_start.weekday())
    week_end = week_start + timedelta(days=6)
    departments = _department_names(conn)
    department = c2.selectbox("Department", departments)
    view_mode = c3.selectbox("View", ["All", "Exceptions only", "Missing logs", "Pending review", "Holidays"])
    if c4.button("Refresh"):
        st.rerun()

    employees, grid, holidays = _load_week(conn, week_start, week_end, department)
    days = [week_start + timedelta(days=i) for i in range(7)]

    def include_emp(emp: dict[str, Any]) -> bool:
        if view_mode == "All":
            return True
        for d in days:
            cell = grid.get((int(emp["id"]), _iso(d)), {})
            label, _icon, _kind = _status_badge(cell, holidays.get(_iso(d)))
            if view_mode == "Exceptions only" and label not in {"OK", "—", "Regular", "Special"}:
                return True
            if view_mode == "Missing logs" and label in {"No log", "Missing out"}:
                return True
            if view_mode == "Pending review" and label in {"Pending", "Needs Manager", "Disputed"}:
                return True
            if view_mode == "Holidays" and _iso(d) in holidays:
                return True
        return False

    employees = [e for e in employees if include_emp(e)]

    st.markdown("**Legend:** 🟢 OK · 🟡 Needs checking · 🔵 Pending · 🔴 Absent/problem · 🟣 Leave · 🎌 Holiday · ⚪ Empty/rest")
    header_cols = st.columns([1.8] + [1] * 7)
    header_cols[0].markdown("**Employee**")
    for i, d in enumerate(days):
        h = holidays.get(_iso(d))
        header_cols[i + 1].markdown(f"**{d.strftime('%a %b %d')}**" + (f"  🎌  \\n{h['name']}" if h else ""))

    for emp in employees:
        cols = st.columns([1.8] + [1] * 7)
        cols[0].markdown(f"**{emp['full_name']}**  \\n<small>{emp.get('employee_code','')} • {emp.get('department','')} • {emp.get('position','')}</small>", unsafe_allow_html=True)
        for i, d in enumerate(days):
            d_iso = _iso(d)
            cell = grid.get((int(emp["id"]), d_iso), {})
            h = holidays.get(d_iso)
            btn_label = _cell_label(d, cell, h)
            if cols[i + 1].button(btn_label, key=f"cal_cell_{emp['id']}_{d_iso}", use_container_width=True):
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(emp["id"]), "date": d_iso}
                st.rerun()

    _open_editor(conn, current_user, audit_func)

    with st.expander("Selected cell editor fallback / direct selector"):
        emp_options = _employee_options(conn, department)
        if not emp_options:
            st.info("No active employees for this filter.")
            return
        e1, e2 = st.columns([2, 1])
        emp_label = e1.selectbox("Employee", list(emp_options.keys()))
        selected_date = e2.date_input("Date to edit", value=week_start, min_value=week_start, max_value=week_end, key="calendar_fallback_date")
        if st.button("Open editor for selected employee/date"):
            st.session_state["calendar_cell_to_edit"] = {"employee_id": int(emp_options[emp_label]), "date": _iso(selected_date)}
            st.rerun()
