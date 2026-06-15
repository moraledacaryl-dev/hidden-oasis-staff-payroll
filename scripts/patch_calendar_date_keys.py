from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'core' / 'calendar_review.py'
s = p.read_text()

# Make the selected editor context visible and stable.
s = s.replace(
    '    st.markdown(f"### {emp.get(\'full_name\',\'Employee\')} — {selected_date.strftime(\'%a, %b %d, %Y\')}")\n',
    '    st.markdown(f"### {emp.get(\'full_name\',\'Employee\')} — {selected_date.strftime(\'%a, %b %d, %Y\')}")\n    st.caption(f"Editing date: {day}")\n'
)

# Explicitly key every editor widget/button by employee + date so button/form state cannot leak to another date.
repls = {
    'a.time_input("Shift start", value=_parse_time((schedule or {}).get("shift_start"), "08:00"))': 'a.time_input("Shift start", value=_parse_time((schedule or {}).get("shift_start"), "08:00"), key=f"shift_start_{employee_id}_{day}")',
    'b.time_input("Shift end", value=_parse_time((schedule or {}).get("shift_end"), "17:00"))': 'b.time_input("Shift end", value=_parse_time((schedule or {}).get("shift_end"), "17:00"), key=f"shift_end_{employee_id}_{day}")',
    'c.number_input("Break minutes", min_value=0, value=default_break, step=15)': 'c.number_input("Break minutes", min_value=0, value=default_break, step=15, key=f"break_minutes_{employee_id}_{day}")',
    'st.selectbox("Department / Area", dept_options, index=dept_idx)': 'st.selectbox("Department / Area", dept_options, index=dept_idx, key=f"sched_dept_{employee_id}_{day}")',
    'st.checkbox("Rest day", value=bool((schedule or {}).get("is_rest_day") or 0))': 'st.checkbox("Rest day", value=bool((schedule or {}).get("is_rest_day") or 0), key=f"sched_rest_{employee_id}_{day}")',
    'st.text_area("Schedule notes", value=str((schedule or {}).get("notes") or ""))': 'st.text_area("Schedule notes", value=str((schedule or {}).get("notes") or ""), key=f"sched_notes_{employee_id}_{day}")',
    'st.form_submit_button("Save schedule", type="primary")': 'st.form_submit_button("Save schedule", type="primary")',
    'a.time_input("Actual in", value=_parse_time((log or {}).get("actual_in"), "08:00"))': 'a.time_input("Actual in", value=_parse_time((log or {}).get("actual_in"), "08:00"), key=f"actual_in_{employee_id}_{day}")',
    'b.time_input("Actual out", value=_parse_time((log or {}).get("actual_out"), "17:00"))': 'b.time_input("Actual out", value=_parse_time((log or {}).get("actual_out"), "17:00"), key=f"actual_out_{employee_id}_{day}")',
    'c.checkbox("No time out yet", value=not bool((log or {}).get("actual_out")))': 'c.checkbox("No time out yet", value=not bool((log or {}).get("actual_out")), key=f"missing_out_{employee_id}_{day}")',
    'st.checkbox("Mark absent", value=bool((log or {}).get("is_absent") or 0))': 'st.checkbox("Mark absent", value=bool((log or {}).get("is_absent") or 0), key=f"absent_{employee_id}_{day}")',
    'st.selectbox("Absence / leave type", absence_options, index=absence_options.index(old_absence) if old_absence in absence_options else 0)': 'st.selectbox("Absence / leave type", absence_options, index=absence_options.index(old_absence) if old_absence in absence_options else 0, key=f"absence_type_{employee_id}_{day}")',
    'd.selectbox("Attendance status", attendance_options, index=attendance_options.index(old_att))': 'd.selectbox("Attendance status", attendance_options, index=attendance_options.index(old_att), key=f"attendance_status_{employee_id}_{day}")',
    'e.selectbox("OT status", ot_options, index=ot_options.index(old_ot))': 'e.selectbox("OT status", ot_options, index=ot_options.index(old_ot), key=f"ot_status_{employee_id}_{day}")',
    'f.number_input("Approved OT hours", min_value=0.0, value=float((log or {}).get("approved_ot_hours") or 0), step=0.25)': 'f.number_input("Approved OT hours", min_value=0.0, value=float((log or {}).get("approved_ot_hours") or 0), step=0.25, key=f"approved_ot_{employee_id}_{day}")',
    'st.text_area("Log / OT notes", value=str((log or {}).get("notes") or ""))': 'st.text_area("Log / OT notes", value=str((log or {}).get("notes") or ""), key=f"log_notes_{employee_id}_{day}")',
    'st.selectbox("Leave type", leave_names)': 'st.selectbox("Leave type", leave_names, key=f"leave_type_{employee_id}_{day}")',
    'st.button("Save approved leave", type="primary")': 'st.button("Save approved leave", type="primary", key=f"save_leave_{employee_id}_{day}")',
    'st.text_input("Holiday name", value=str((holiday or {}).get("name") or ""))': 'st.text_input("Holiday name", value=str((holiday or {}).get("name") or ""), key=f"holiday_name_{day}")',
    'st.selectbox("Holiday type", ["Regular", "Special"], index=0 if (holiday or {}).get("holiday_type") != "Special" else 1)': 'st.selectbox("Holiday type", ["Regular", "Special"], index=0 if (holiday or {}).get("holiday_type") != "Special" else 1, key=f"holiday_type_{day}")',
    'st.text_area("Holiday notes", value=str((holiday or {}).get("notes") or ""))': 'st.text_area("Holiday notes", value=str((holiday or {}).get("notes") or ""), key=f"holiday_notes_{day}")',
    'q1.button("Mark reviewed")': 'q1.button("Mark reviewed", key=f"quick_reviewed_{employee_id}_{day}")',
    'q2.button("Rest day")': 'q2.button("Rest day", key=f"quick_rest_{employee_id}_{day}")',
    'q3.button("Copy S → A")': 'q3.button("Copy S → A", key=f"quick_copy_{employee_id}_{day}")',
    'q4.button("Absent")': 'q4.button("Absent", key=f"quick_absent_{employee_id}_{day}")',
}
for old, new in repls.items():
    if old in s:
        s = s.replace(old, new)

# Keep the editor open on the same exact date after saving, instead of letting any fallback/default date become active.
s = s.replace('                st.success("Schedule saved.")\n                st.rerun()', '                st.session_state["calendar_cell_to_edit"] = {"employee_id": employee_id, "date": day}\n                st.success("Schedule saved.")\n                st.rerun()')
s = s.replace('            st.success("Rest day saved.")\n            st.rerun()', '            st.session_state["calendar_cell_to_edit"] = {"employee_id": employee_id, "date": day}\n            st.success("Rest day saved.")\n            st.rerun()')

p.write_text(s)
print('Patched Calendar Review editor widgets/buttons with employee-date keys.')
