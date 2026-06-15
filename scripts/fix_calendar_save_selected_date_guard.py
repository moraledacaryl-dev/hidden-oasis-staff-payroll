from pathlib import Path

p = Path('core/calendar_review.py')
s = p.read_text()

start = s.find('def _save_schedule(')
mid = s.find('\ndef _save_log(', start)
end = s.find('\ndef _save_holiday(', mid)
if start < 0 or mid < 0 or end < 0:
    raise SystemExit('Could not find calendar save function block.')

replacement = r'''def _save_schedule(conn, employee_id: int, work_date: str, shift_start: str, shift_end: str, break_minutes: int, department: str, rest_day: bool, notes: str, schedule_id: int | None = None) -> None:
    # Source of truth is the currently selected calendar cell: employee_id + work_date.
    # Existing row id is used only when it belongs to the same selected employee/date.
    valid_schedule_id = None
    if schedule_id:
        row = fetchone(conn, "SELECT id FROM schedules WHERE id=? AND employee_id=? AND work_date=?", (schedule_id, employee_id, work_date))
        if row:
            valid_schedule_id = schedule_id

    if valid_schedule_id:
        execute(
            conn,
            "UPDATE schedules SET shift_start=?, shift_end=?, break_minutes=?, department=?, location=?, is_rest_day=?, notes=? WHERE id=? AND employee_id=? AND work_date=?",
            (shift_start, shift_end, int(break_minutes), department, department, int(rest_day), notes, valid_schedule_id, employee_id, work_date),
        )
    else:
        existing = fetchone(conn, "SELECT id FROM schedules WHERE employee_id=? AND work_date=? ORDER BY id DESC LIMIT 1", (employee_id, work_date))
        if existing:
            execute(
                conn,
                "UPDATE schedules SET shift_start=?, shift_end=?, break_minutes=?, department=?, location=?, is_rest_day=?, notes=? WHERE id=? AND employee_id=? AND work_date=?",
                (shift_start, shift_end, int(break_minutes), department, department, int(rest_day), notes, int(existing["id"]), employee_id, work_date),
            )
        else:
            execute(
                conn,
                "INSERT INTO schedules(employee_id, work_date, shift_start, shift_end, break_minutes, department, location, is_rest_day, notes) VALUES(?,?,?,?,?,?,?,?,?)",
                (employee_id, work_date, shift_start, shift_end, int(break_minutes), department, department, int(rest_day), notes),
            )


def _save_log(conn, employee_id: int, work_date: str, actual_in: str, actual_out: str, absent: bool, absence_type: str, approved_ot: float, ot_status: str, attendance_status: str, notes: str, log_id: int | None = None) -> None:
    # Source of truth is the currently selected calendar cell: employee_id + work_date.
    # Existing row id is used only when it belongs to the same selected employee/date.
    valid_log_id = None
    if log_id:
        row = fetchone(conn, "SELECT id FROM time_logs WHERE id=? AND employee_id=? AND work_date=?", (log_id, employee_id, work_date))
        if row:
            valid_log_id = log_id

    if valid_log_id:
        execute(
            conn,
            "UPDATE time_logs SET actual_in=?, actual_out=?, source='calendar', verification_type='Calendar Review', is_absent=?, absence_type=?, approved_ot_hours=?, ot_status=?, attendance_status=?, notes=?, updated_at=? WHERE id=? AND employee_id=? AND work_date=?",
            (actual_in, actual_out, int(absent), absence_type, float(approved_ot), ot_status, attendance_status, notes, now_iso(), valid_log_id, employee_id, work_date),
        )
    else:
        existing = fetchone(conn, "SELECT id FROM time_logs WHERE employee_id=? AND work_date=? ORDER BY id DESC LIMIT 1", (employee_id, work_date))
        if existing:
            execute(
                conn,
                "UPDATE time_logs SET actual_in=?, actual_out=?, source='calendar', verification_type='Calendar Review', is_absent=?, absence_type=?, approved_ot_hours=?, ot_status=?, attendance_status=?, notes=?, updated_at=? WHERE id=? AND employee_id=? AND work_date=?",
                (actual_in, actual_out, int(absent), absence_type, float(approved_ot), ot_status, attendance_status, notes, now_iso(), int(existing["id"]), employee_id, work_date),
            )
        else:
            execute(
                conn,
                "INSERT INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type, is_absent, absence_type, approved_ot_hours, ot_status, attendance_status, notes, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (employee_id, work_date, actual_in, actual_out, "calendar", "Calendar Review", int(absent), absence_type, float(approved_ot), ot_status, attendance_status, notes, now_iso(), now_iso()),
            )

'''

s = s[:start] + replacement + s[end + 1:]

# Add visible selected-date debug line in the popup editor if it is not already present.
marker = '    st.markdown(f"### {emp.get(\'full_name\',\'Employee\')} — {selected_date.strftime(\'%a, %b %d, %Y\')}")\n'
insert = marker + '    st.warning(f"DEBUG selected save date: {day} | employee_id: {employee_id}")\n'
if marker in s and 'DEBUG selected save date:' not in s:
    s = s.replace(marker, insert, 1)

p.write_text(s)
print('Patched calendar schedule/log saves to selected employee/date with stale-id guard.')
