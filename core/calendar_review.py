from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
import html

import streamlit as st

from .db import execute, fetchall, fetchone, now_iso


def _iso(d: date | str | None) -> str:
    return "" if d is None else (d.isoformat() if isinstance(d, date) else str(d))


def _time_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S"):
        try:
            t = datetime.strptime(text, fmt)
            return t.strftime("%I:%M%p").lstrip("0").lower().replace("m", "")
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


def _h(value: Any) -> str:
    return html.escape(str(value or ""))


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
    grid: dict[tuple[int, str], dict[str, Any]] = {}
    holidays = {
        str(h["holiday_date"]): h
        for h in fetchall(conn, "SELECT * FROM holidays WHERE active=1 AND holiday_date BETWEEN ? AND ?", (_iso(start), _iso(end)))
    }
    emp_ids = [int(e["id"]) for e in employees]
    if not emp_ids:
        return employees, grid, holidays
    ph = ",".join(["?"] * len(emp_ids))
    schedules = fetchall(conn, f"SELECT * FROM schedules WHERE employee_id IN ({ph}) AND work_date BETWEEN ? AND ? ORDER BY work_date, shift_start", (*emp_ids, _iso(start), _iso(end)))
    logs = fetchall(conn, f"SELECT * FROM time_logs WHERE employee_id IN ({ph}) AND work_date BETWEEN ? AND ? ORDER BY work_date, actual_in", (*emp_ids, _iso(start), _iso(end)))
    for row in schedules:
        grid.setdefault((int(row["employee_id"]), str(row["work_date"])), {})["schedule"] = row
    for row in logs:
        grid.setdefault((int(row["employee_id"]), str(row["work_date"])), {})["log"] = row
    return employees, grid, holidays


def _status(cell: dict[str, Any], holiday: dict[str, Any] | None = None) -> tuple[str, str, str]:
    schedule = cell.get("schedule")
    log = cell.get("log")
    if log and int(log.get("is_absent") or 0):
        absence = str(log.get("absence_type") or "Absent")
        if any(word in absence.lower() for word in ("leave", "sick", "bereavement", "service")):
            return absence, "🟣", "leave"
        return absence, "🔴", "absent"
    if log and str(log.get("absence_type") or "").strip():
        return str(log.get("absence_type")), "🟣", "leave"
    if holiday:
        return str(holiday.get("holiday_type") or "Holiday"), "🎌", "holiday"
    if schedule and int(schedule.get("is_rest_day") or 0):
        return "Rest day", "⚪", "rest"
    if schedule and not log:
        return "Scheduled", "🟡", "scheduled"
    if log and not str(log.get("actual_out") or "").strip() and not int(log.get("is_absent") or 0):
        return "Missing out", "🟡", "late"
    if log and str(log.get("attendance_status") or "").lower() in {"pending", "needs manager", "disputed"}:
        return str(log.get("attendance_status") or "Pending"), "🔵", "pending"
    if log and "late" in str(log.get("notes") or "").lower():
        return "Late", "🟡", "late"
    if schedule or log:
        return "OK", "🟢", "ok"
    return "Empty", "⚪", "empty"


def _short(label: str) -> str:
    return {
        "Service Incentive Leave": "SIL",
        "Sick Leave": "Sick leave",
        "Bereavement Leave": "BL",
        "Needs Manager": "Needs mgr",
        "Regular": "Regular hol",
        "Special": "Special hol",
    }.get(label, label[:14])


def _cell_card_html(day: date, cell: dict[str, Any], holiday: dict[str, Any] | None) -> str:
    schedule = cell.get("schedule")
    log = cell.get("log")
    label, icon, kind = _status(cell, holiday)
    if schedule and int(schedule.get("is_rest_day") or 0):
        s_text = "Rest"
    elif schedule:
        s_text = f"{_time_text(schedule.get('shift_start'))}-{_time_text(schedule.get('shift_end'))}"
    else:
        s_text = "—"
    if log and int(log.get("is_absent") or 0):
        a_text = str(log.get("absence_type") or "Absent")
    elif log:
        a_text = f"{_time_text(log.get('actual_in'))}-{_time_text(log.get('actual_out')) or '—'}"
    else:
        a_text = "—"
    mini_holiday = f"<div class='cal-mini'>🎌 {_h(holiday['name'])}</div>" if holiday else ""
    return f"""
    <div class="cal-card cal-{kind}">
      <div class="cal-top"><span>{icon}</span><span>{day.strftime('%a %d')}</span></div>
      <div class="cal-status">{_h(_short(label))}</div>
      <div class="cal-line"><b>S</b> {_h(s_text)}</div>
      <div class="cal-line"><b>A</b> {_h(a_text)}</div>
      {mini_holiday}
    </div>
    """


def _calendar_css() -> None:
    st.markdown(
        """
        <style>
        .cal-legend{border:1px solid #e7dfd5;background:#fffaf2;border-radius:16px;padding:10px 12px;margin:8px 0 12px;color:#584f45;font-size:.86rem;}
        .cal-header{height:56px;min-height:56px;border:1px solid #e6dccc;border-radius:14px;background:#f8f2e9;padding:9px 10px;font-weight:800;color:#3f372f;box-sizing:border-box;overflow:hidden;}
        .cal-header-sub{font-size:.68rem;color:#8a5b0a;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px;}
        .cal-emp{height:116px;min-height:116px;max-height:116px;border:1px solid #e4dbcf;border-radius:14px;background:#fffdf8;padding:12px;box-sizing:border-box;overflow:hidden;display:flex;flex-direction:column;justify-content:center;}
        .cal-emp-name{font-weight:800;color:#2f2923;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:5px;}
        .cal-emp-meta{font-size:.72rem;color:#74695f;line-height:1.25;}
        .cal-card{height:86px;min-height:86px;max-height:86px;border-radius:14px;border:1px solid #ded4c8;padding:9px 10px;box-sizing:border-box;overflow:hidden;color:#302a24;}
        .cal-top{display:flex;gap:5px;align-items:center;font-size:.76rem;font-weight:800;white-space:nowrap;}
        .cal-status{font-size:.72rem;font-weight:800;margin:4px 0 5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
        .cal-line{font-size:.69rem;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
        .cal-mini{display:block;margin-top:3px;font-size:.62rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#8a5b0a;font-weight:700;}
        .cal-empty{background:#f3f1ee;border-color:#ddd8d1;color:#77716a;}
        .cal-rest{background:#eeeae3;border-color:#d6cec4;color:#6e665f;}
        .cal-scheduled{background:#fff8df;border-color:#e6c96d;}
        .cal-ok{background:#edf8ee;border-color:#9fd3a4;}
        .cal-late{background:#fff0cd;border-color:#e2b341;}
        .cal-pending{background:#e8f0ff;border-color:#9fbde9;}
        .cal-absent{background:#ffe7e2;border-color:#e69a90;}
        .cal-leave{background:#f1e7ff;border-color:#c5a6ed;}
        .cal-holiday{background:#fff3d2;border-color:#d9ac45;}
        div[data-testid="column"] .stButton > button {height:26px;min-height:26px;padding:0 8px;font-size:.72rem;border-radius:10px;margin-top:4px;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _save_schedule(conn, employee_id: int, work_date: str, shift_start: str, shift_end: str, break_minutes: int, department: str, rest_day: bool, notes: str, schedule_id: int | None = None) -> None:
    if schedule_id:
        execute(conn, "UPDATE schedules SET shift_start=?, shift_end=?, break_minutes=?, department=?, location=?, is_rest_day=?, notes=? WHERE id=?", (shift_start, shift_end, int(break_minutes), department, department, int(rest_day), notes, schedule_id))
    else:
        execute(conn, "INSERT OR REPLACE INTO schedules(employee_id, work_date, shift_start, shift_end, break_minutes, department, location, is_rest_day, notes) VALUES(?,?,?,?,?,?,?,?,?)", (employee_id, work_date, shift_start, shift_end, int(break_minutes), department, department, int(rest_day), notes))


def _save_log(conn, employee_id: int, work_date: str, actual_in: str, actual_out: str, absent: bool, absence_type: str, approved_ot: float, ot_status: str, attendance_status: str, notes: str, log_id: int | None = None) -> None:
    if log_id:
        execute(conn, "UPDATE time_logs SET actual_in=?, actual_out=?, source='calendar', verification_type='Calendar Review', is_absent=?, absence_type=?, approved_ot_hours=?, ot_status=?, attendance_status=?, notes=?, updated_at=? WHERE id=?", (actual_in, actual_out, int(absent), absence_type, float(approved_ot), ot_status, attendance_status, notes, now_iso(), log_id))
    else:
        execute(conn, "INSERT INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type, is_absent, absence_type, approved_ot_hours, ot_status, attendance_status, notes, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (employee_id, work_date, actual_in, actual_out, "calendar", "Calendar Review", int(absent), absence_type, float(approved_ot), ot_status, attendance_status, notes, now_iso(), now_iso()))


def _save_holiday(conn, holiday_date: str, name: str, holiday_type: str, notes: str) -> None:
    execute(conn, "INSERT INTO holidays(holiday_date, name, holiday_type, active, notes, created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(holiday_date) DO UPDATE SET name=excluded.name, holiday_type=excluded.holiday_type, active=excluded.active, notes=excluded.notes", (holiday_date, name, holiday_type, 1, notes, now_iso()))


def _leave_type_id(conn, name: str) -> int:
    row = fetchone(conn, "SELECT id FROM leave_types WHERE lower(name)=lower(?)", (name,))
    if not row:
        execute(conn, "INSERT INTO leave_types(name, default_credits, paid, statutory, requires_approval, active, notes) VALUES(?,?,?,?,?,?,?)", (name, 0, 1, 0, 1, 1, "Created from Calendar Review"))
        row = fetchone(conn, "SELECT id FROM leave_types WHERE lower(name)=lower(?)", (name,))
    return int(row["id"])


def _mark_leave(conn, employee_id: int, day: str, leave_name: str, actor: str) -> None:
    lt_id = _leave_type_id(conn, leave_name)
    execute(conn, "INSERT INTO leave_requests(employee_id, leave_type_id, start_date, end_date, days, paid, status, reason, reviewed_by, reviewed_at, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (employee_id, lt_id, day, day, 1, 1, "Approved", "Calendar Review quick action", actor, now_iso(), now_iso()))
    existing = fetchone(conn, "SELECT id FROM time_logs WHERE employee_id=? AND work_date=? ORDER BY id DESC LIMIT 1", (employee_id, day))
    _save_log(conn, employee_id, day, "", "", True, leave_name, 0, "None", "Reviewed", f"Marked {leave_name} from Calendar Review", int(existing["id"]) if existing else None)


def _render_editor(conn, current_user: str, employee_id: int, selected_date: date, audit_func=None) -> None:
    day = _iso(selected_date)
    emp = fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,)) or {}
    schedule = fetchone(conn, "SELECT * FROM schedules WHERE employee_id=? AND work_date=? ORDER BY shift_start LIMIT 1", (employee_id, day))
    log = fetchone(conn, "SELECT * FROM time_logs WHERE employee_id=? AND work_date=? ORDER BY id DESC LIMIT 1", (employee_id, day))
    holiday = fetchone(conn, "SELECT * FROM holidays WHERE holiday_date=? AND active=1", (day,))
    st.markdown(f"### {emp.get('full_name','Employee')} — {selected_date.strftime('%a, %b %d, %Y')}")
    tabs = st.tabs(["Schedule", "Actual / OT", "Leave", "Holiday", "Quick"])

    with tabs[0]:
        with st.form(f"sched_{employee_id}_{day}"):
            a, b, c = st.columns(3)
            shift_start = a.time_input("Shift start", value=_parse_time((schedule or {}).get("shift_start"), "08:00"))
            shift_end = b.time_input("Shift end", value=_parse_time((schedule or {}).get("shift_end"), "17:00"))
            default_break = int((schedule or {}).get("break_minutes") or (0 if str(emp.get("department", "")).lower() == "security" else 60))
            break_minutes = c.number_input("Break minutes", min_value=0, value=default_break, step=15)
            dept_options = [""] + _department_names(conn, include_all=False)
            default_dept = (schedule or {}).get("department") or emp.get("department") or ""
            dept_idx = dept_options.index(default_dept) if default_dept in dept_options else 0
            dept = st.selectbox("Department / Area", dept_options, index=dept_idx)
            rest = st.checkbox("Rest day", value=bool((schedule or {}).get("is_rest_day") or 0))
            notes = st.text_area("Schedule notes", value=str((schedule or {}).get("notes") or ""))
            if st.form_submit_button("Save schedule", type="primary"):
                _save_schedule(conn, employee_id, day, shift_start.strftime("%H:%M"), shift_end.strftime("%H:%M"), int(break_minutes), dept, rest, notes, int(schedule["id"]) if schedule else None)
                st.success("Schedule saved.")
                st.rerun()

    with tabs[1]:
        with st.form(f"log_{employee_id}_{day}"):
            a, b, c = st.columns(3)
            actual_in = a.time_input("Actual in", value=_parse_time((log or {}).get("actual_in"), "08:00"))
            actual_out = b.time_input("Actual out", value=_parse_time((log or {}).get("actual_out"), "17:00"))
            missing_out = c.checkbox("No time out yet", value=not bool((log or {}).get("actual_out")))
            absent = st.checkbox("Mark absent", value=bool((log or {}).get("is_absent") or 0))
            absence_options = ["", "Absent", "Service Incentive Leave", "Sick Leave", "Bereavement Leave", "Unpaid Leave"]
            old_absence = str((log or {}).get("absence_type") or "")
            absence_type = st.selectbox("Absence / leave type", absence_options, index=absence_options.index(old_absence) if old_absence in absence_options else 0)
            d, e, f = st.columns(3)
            attendance_options = ["Pending", "Reviewed", "Needs Manager", "Disputed"]
            old_att = (log or {}).get("attendance_status") if (log or {}).get("attendance_status") in attendance_options else "Pending"
            attendance_status = d.selectbox("Attendance status", attendance_options, index=attendance_options.index(old_att))
            ot_options = ["None", "Pending", "Approved", "Rejected"]
            old_ot = (log or {}).get("ot_status") if (log or {}).get("ot_status") in ot_options else "None"
            ot_status = e.selectbox("OT status", ot_options, index=ot_options.index(old_ot))
            approved_ot = f.number_input("Approved OT hours", min_value=0.0, value=float((log or {}).get("approved_ot_hours") or 0), step=0.25)
            notes = st.text_area("Log / OT notes", value=str((log or {}).get("notes") or ""))
            if st.form_submit_button("Save actual / OT", type="primary"):
                in_text = "" if absent else actual_in.strftime("%H:%M")
                out_text = "" if absent or missing_out else actual_out.strftime("%H:%M")
                _save_log(conn, employee_id, day, in_text, out_text, absent, absence_type, approved_ot, ot_status, attendance_status, notes, int(log["id"]) if log else None)
                st.success("Actual log saved.")
                st.rerun()

    with tabs[2]:
        leave_names = [r["name"] for r in fetchall(conn, "SELECT name FROM leave_types WHERE active=1 ORDER BY name")] or ["Service Incentive Leave", "Sick Leave", "Bereavement Leave", "Unpaid Leave"]
        leave_name = st.selectbox("Leave type", leave_names)
        if st.button("Save approved leave", type="primary"):
            _mark_leave(conn, employee_id, day, leave_name, current_user)
            st.success("Leave saved.")
            st.rerun()

    with tabs[3]:
        with st.form(f"holiday_{day}"):
            hname = st.text_input("Holiday name", value=str((holiday or {}).get("name") or ""))
            htype = st.selectbox("Holiday type", ["Regular", "Special"], index=0 if (holiday or {}).get("holiday_type") != "Special" else 1)
            hnotes = st.text_area("Holiday notes", value=str((holiday or {}).get("notes") or ""))
            if st.form_submit_button("Save holiday for this date", type="primary"):
                if not hname.strip():
                    st.error("Holiday name is required.")
                else:
                    _save_holiday(conn, day, hname.strip(), htype, hnotes)
                    st.success("Holiday saved.")
                    st.rerun()

    with tabs[4]:
        q1, q2, q3, q4 = st.columns(4)
        if q1.button("Mark reviewed"):
            if log:
                execute(conn, "UPDATE time_logs SET attendance_status='Reviewed', reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?", (current_user, now_iso(), now_iso(), int(log["id"])))
            else:
                _save_log(conn, employee_id, day, "", "", False, "", 0, "None", "Reviewed", "Reviewed empty day", None)
            st.success("Reviewed.")
            st.rerun()
        if q2.button("Rest day"):
            _save_schedule(conn, employee_id, day, "00:00", "00:00", 0, str(emp.get("department") or ""), True, "Marked rest day", int(schedule["id"]) if schedule else None)
            st.success("Rest day saved.")
            st.rerun()
        if q3.button("Copy S → A") and schedule:
            _save_log(conn, employee_id, day, str(schedule["shift_start"]), str(schedule["shift_end"]), False, "", 0, "None", "Reviewed", "Copied schedule to actual", int(log["id"]) if log else None)
            st.success("Copied.")
            st.rerun()
        if q4.button("Absent"):
            _save_log(conn, employee_id, day, "", "", True, "Absent", 0, "None", "Reviewed", "Marked absent", int(log["id"]) if log else None)
            st.success("Absent saved.")
            st.rerun()


def render_calendar_review(conn, current_user: str, audit_func=None) -> None:
    st.title("Calendar Review")
    st.caption("Same-size semi-colored calendar cells. Use the Edit button inside a cell; this keeps you logged in and opens the popup without navigating away.")
    _calendar_css()
    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    week_start = c1.date_input("Week start", value=date.today() - timedelta(days=date.today().weekday()))
    week_start = week_start - timedelta(days=week_start.weekday())
    week_end = week_start + timedelta(days=6)
    department = c2.selectbox("Department", _department_names(conn))
    view_mode = c3.selectbox("View", ["All", "Exceptions only", "Missing logs", "Pending review", "Holidays"])
    if c4.button("Refresh"):
        st.rerun()
    employees, grid, holidays = _load_week(conn, week_start, week_end, department)
    days = [week_start + timedelta(days=i) for i in range(7)]

    def include_emp(emp: dict[str, Any]) -> bool:
        if view_mode == "All":
            return True
        for d in days:
            label, _icon, _kind = _status(grid.get((int(emp["id"]), _iso(d)), {}), holidays.get(_iso(d)))
            if view_mode == "Exceptions only" and label not in {"OK", "Empty", "Regular", "Special"}:
                return True
            if view_mode == "Missing logs" and label in {"Scheduled", "Missing out"}:
                return True
            if view_mode == "Pending review" and label in {"Pending", "Needs Manager", "Disputed"}:
                return True
            if view_mode == "Holidays" and _iso(d) in holidays:
                return True
        return False

    employees = [e for e in employees if include_emp(e)]
    st.markdown("<div class='cal-legend'><b>Legend:</b> green OK · yellow scheduled/late/missing · blue pending · red absent · purple leave · gold holiday · gray empty/rest</div>", unsafe_allow_html=True)

    header = st.columns([1.35] + [1] * 7)
    header[0].markdown("<div class='cal-header'>Employee</div>", unsafe_allow_html=True)
    for i, d in enumerate(days):
        holiday = holidays.get(_iso(d))
        sub = f"<div class='cal-header-sub'>🎌 {_h(holiday['name'])}</div>" if holiday else ""
        header[i + 1].markdown(f"<div class='cal-header'>{d.strftime('%a %b %d')}{sub}</div>", unsafe_allow_html=True)

    for emp in employees:
        cols = st.columns([1.35] + [1] * 7)
        cols[0].markdown(f"<div class='cal-emp'><div class='cal-emp-name'>{_h(emp['full_name'])}</div><div class='cal-emp-meta'>{_h(emp.get('employee_code',''))}<br>{_h(emp.get('department',''))} • {_h(emp.get('position',''))}</div></div>", unsafe_allow_html=True)
        for i, d in enumerate(days):
            d_iso = _iso(d)
            cols[i + 1].markdown(_cell_card_html(d, grid.get((int(emp["id"]), d_iso), {}), holidays.get(d_iso)), unsafe_allow_html=True)
            if cols[i + 1].button("Edit", key=f"edit_cal_{emp['id']}_{d_iso}", use_container_width=True):
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(emp["id"]), "date": d_iso}
                st.rerun()

    payload = st.session_state.get("calendar_cell_to_edit")
    if payload:
        selected_date = datetime.strptime(str(payload["date"]), "%Y-%m-%d").date()
        employee_id = int(payload["employee_id"])
        if hasattr(st, "dialog"):
            @st.dialog("Edit schedule / actual / leave / holiday / OT", width="large")
            def popup() -> None:
                _render_editor(conn, current_user, employee_id, selected_date, audit_func)
                if st.button("Close"):
                    st.session_state.pop("calendar_cell_to_edit", None)
                    st.rerun()
            popup()
        else:
            st.markdown("---")
            _render_editor(conn, current_user, employee_id, selected_date, audit_func)

    with st.expander("Direct selector fallback"):
        opts = _employee_options(conn, department)
        if opts:
            left, right = st.columns([2, 1])
            emp_label = left.selectbox("Employee", list(opts.keys()))
            selected_date = right.date_input("Date", value=week_start, min_value=week_start, max_value=week_end, key="fallback_cal_date")
            if st.button("Open editor"):
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(opts[emp_label]), "date": _iso(selected_date)}
                st.rerun()
