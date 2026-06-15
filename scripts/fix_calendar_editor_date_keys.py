from pathlib import Path

CAL = Path(__file__).resolve().parents[1] / "core" / "calendar_review.py"
s = CAL.read_text()

# Add a stable key prefix tied to the employee/date being edited.
old = '    day = _iso(selected_date)\n    emp = fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,)) or {}'
new = '    day = _iso(selected_date)\n    key_prefix = f"cal_editor_{employee_id}_{day}"\n    emp = fetchone(conn, "SELECT * FROM employees WHERE id=?", (employee_id,)) or {}'
if old in s and 'key_prefix = f"cal_editor_{employee_id}_{day}"' not in s:
    s = s.replace(old, new, 1)

replacements = {
    'shift_start = a.time_input("Shift start", value=_parse_time((schedule or {}).get("shift_start"), "08:00"))':
    'shift_start = a.time_input("Shift start", value=_parse_time((schedule or {}).get("shift_start"), "08:00"), key=f"{key_prefix}_shift_start")',

    'shift_end = b.time_input("Shift end", value=_parse_time((schedule or {}).get("shift_end"), "17:00"))':
    'shift_end = b.time_input("Shift end", value=_parse_time((schedule or {}).get("shift_end"), "17:00"), key=f"{key_prefix}_shift_end")',

    'break_minutes = c.number_input("Break minutes", min_value=0, value=default_break, step=15)':
    'break_minutes = c.number_input("Break minutes", min_value=0, value=default_break, step=15, key=f"{key_prefix}_break_minutes")',

    'dept = st.selectbox("Department / Area", dept_options, index=dept_idx)':
    'dept = st.selectbox("Department / Area", dept_options, index=dept_idx, key=f"{key_prefix}_dept")',

    'rest = st.checkbox("Rest day", value=bool((schedule or {}).get("is_rest_day") or 0))':
    'rest = st.checkbox("Rest day", value=bool((schedule or {}).get("is_rest_day") or 0), key=f"{key_prefix}_rest")',

    'notes = st.text_area("Schedule notes", value=str((schedule or {}).get("notes") or ""))':
    'notes = st.text_area("Schedule notes", value=str((schedule or {}).get("notes") or ""), key=f"{key_prefix}_schedule_notes")',

    'actual_in = a.time_input("Actual in", value=_parse_time((log or {}).get("actual_in"), "08:00"))':
    'actual_in = a.time_input("Actual in", value=_parse_time((log or {}).get("actual_in"), "08:00"), key=f"{key_prefix}_actual_in")',

    'actual_out = b.time_input("Actual out", value=_parse_time((log or {}).get("actual_out"), "17:00"))':
    'actual_out = b.time_input("Actual out", value=_parse_time((log or {}).get("actual_out"), "17:00"), key=f"{key_prefix}_actual_out")',

    'missing_out = c.checkbox("No time out yet", value=not bool((log or {}).get("actual_out")))':
    'missing_out = c.checkbox("No time out yet", value=not bool((log or {}).get("actual_out")), key=f"{key_prefix}_missing_out")',

    'absent = st.checkbox("Mark absent", value=bool((log or {}).get("is_absent") or 0))':
    'absent = st.checkbox("Mark absent", value=bool((log or {}).get("is_absent") or 0), key=f"{key_prefix}_absent")',

    'absence_type = st.selectbox("Absence / leave type", absence_options, index=absence_options.index(old_absence) if old_absence in absence_options else 0)':
    'absence_type = st.selectbox("Absence / leave type", absence_options, index=absence_options.index(old_absence) if old_absence in absence_options else 0, key=f"{key_prefix}_absence_type")',

    'attendance_status = d.selectbox("Attendance status", attendance_options, index=attendance_options.index(old_att))':
    'attendance_status = d.selectbox("Attendance status", attendance_options, index=attendance_options.index(old_att), key=f"{key_prefix}_attendance_status")',

    'ot_status = e.selectbox("OT status", ot_options, index=ot_options.index(old_ot))':
    'ot_status = e.selectbox("OT status", ot_options, index=ot_options.index(old_ot), key=f"{key_prefix}_ot_status")',

    'approved_ot = f.number_input("Approved OT hours", min_value=0.0, value=float((log or {}).get("approved_ot_hours") or 0), step=0.25)':
    'approved_ot = f.number_input("Approved OT hours", min_value=0.0, value=float((log or {}).get("approved_ot_hours") or 0), step=0.25, key=f"{key_prefix}_approved_ot")',

    'notes = st.text_area("Log / OT notes", value=str((log or {}).get("notes") or ""))':
    'notes = st.text_area("Log / OT notes", value=str((log or {}).get("notes") or ""), key=f"{key_prefix}_log_notes")',

    'leave_name = st.selectbox("Leave type", leave_names)':
    'leave_name = st.selectbox("Leave type", leave_names, key=f"{key_prefix}_leave_name")',

    'if st.button("Save approved leave", type="primary"):' :
    'if st.button("Save approved leave", type="primary", key=f"{key_prefix}_save_leave"):',

    'hname = st.text_input("Holiday name", value=str((holiday or {}).get("name") or ""))':
    'hname = st.text_input("Holiday name", value=str((holiday or {}).get("name") or ""), key=f"{key_prefix}_holiday_name")',

    'htype = st.selectbox("Holiday type", ["Regular", "Special"], index=0 if (holiday or {}).get("holiday_type") != "Special" else 1)':
    'htype = st.selectbox("Holiday type", ["Regular", "Special"], index=0 if (holiday or {}).get("holiday_type") != "Special" else 1, key=f"{key_prefix}_holiday_type")',

    'hnotes = st.text_area("Holiday notes", value=str((holiday or {}).get("notes") or ""))':
    'hnotes = st.text_area("Holiday notes", value=str((holiday or {}).get("notes") or ""), key=f"{key_prefix}_holiday_notes")',

    'if q1.button("Mark reviewed"):' :
    'if q1.button("Mark reviewed", key=f"{key_prefix}_mark_reviewed"):',

    'if q2.button("Rest day"):' :
    'if q2.button("Rest day", key=f"{key_prefix}_rest_day_quick"):',

    'if q3.button("Copy S → A") and schedule:' :
    'if q3.button("Copy S → A", key=f"{key_prefix}_copy_schedule_actual") and schedule:',

    'if q4.button("Absent"):' :
    'if q4.button("Absent", key=f"{key_prefix}_absent_quick"):',
}

changed = 0
for old, new in replacements.items():
    if new in s:
        continue
    if old not in s:
        print(f"Missing expected snippet, skipped: {old[:80]}")
        continue
    s = s.replace(old, new, 1)
    changed += 1

# After saving, keep the editor pointed at the same employee/date explicitly.
# This prevents a rerun from reusing another previously clicked date payload.
old_save = '                st.success("Actual log saved.")\n                st.rerun()'
new_save = '                st.session_state["calendar_cell_to_edit"] = {"employee_id": employee_id, "date": day}\n                st.success("Actual log saved.")\n                st.rerun()'
if old_save in s and new_save not in s:
    s = s.replace(old_save, new_save, 1)

old_sched = '                st.success("Schedule saved.")\n                st.rerun()'
new_sched = '                st.session_state["calendar_cell_to_edit"] = {"employee_id": employee_id, "date": day}\n                st.success("Schedule saved.")\n                st.rerun()'
if old_sched in s and new_sched not in s:
    s = s.replace(old_sched, new_sched, 1)

CAL.write_text(s)
print(f"Applied calendar editor date-specific widget keys. Changed {changed} widgets/buttons.")
