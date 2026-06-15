from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'core' / 'calendar_review.py'
s = p.read_text()

old = '''    emp_id, day_iso = _query_params()
    if emp_id and day_iso:
        try:
            selected_date = datetime.strptime(day_iso, "%Y-%m-%d").date()
            if hasattr(st, "dialog"):
                @st.dialog("Edit schedule / actual / leave / holiday / OT", width="large")
                def popup() -> None:
                    _render_editor(conn, current_user, emp_id, selected_date, audit_func)
                    if st.button("Close"):
                        _clear_query()
                        st.rerun()
                popup()
            else:
                st.markdown("---")
                _render_editor(conn, current_user, emp_id, selected_date, audit_func)
        except Exception as exc:
            st.error(f"Could not open calendar cell: {exc}")
'''

new = '''    emp_id, day_iso = _query_params()
    if emp_id and day_iso:
        st.session_state["calendar_cell_to_edit"] = {"employee_id": int(emp_id), "date": str(day_iso)}
        _clear_query()
        st.rerun()

    payload = st.session_state.get("calendar_cell_to_edit")
    if payload:
        try:
            employee_id = int(payload["employee_id"])
            selected_date = datetime.strptime(str(payload["date"]), "%Y-%m-%d").date()
            if hasattr(st, "dialog"):
                @st.dialog("Edit schedule / actual / leave / holiday / OT", width="large")
                def popup() -> None:
                    _render_editor(conn, current_user, employee_id, selected_date, audit_func)
                    if st.button("Close", key=f"close_calendar_editor_{employee_id}_{payload['date']}"):
                        st.session_state.pop("calendar_cell_to_edit", None)
                        st.rerun()
                popup()
            else:
                st.markdown("---")
                _render_editor(conn, current_user, employee_id, selected_date, audit_func)
        except Exception as exc:
            st.session_state.pop("calendar_cell_to_edit", None)
            st.error(f"Could not open calendar cell: {exc}")
'''

if old not in s:
    print('HTML query-param editor block not found; checking native session-state block.')
else:
    s = s.replace(old, new, 1)

# Add a visible safety line in editor so the user can confirm the exact saved date.
old_heading = "    st.markdown(f\"### {emp.get('full_name','Employee')} — {selected_date.strftime('%a, %b %d, %Y')}\")\n"
if old_heading in s and 'Editing date:' not in s:
    s = s.replace(old_heading, old_heading + '    st.caption(f"Editing date: {day}")\n', 1)

# Key quick buttons by employee/date where present.
repls = {
    'q1.button("Mark reviewed")': 'q1.button("Mark reviewed", key=f"quick_reviewed_{employee_id}_{day}")',
    'q2.button("Rest day")': 'q2.button("Rest day", key=f"quick_rest_{employee_id}_{day}")',
    'q3.button("Copy S → A")': 'q3.button("Copy S → A", key=f"quick_copy_{employee_id}_{day}")',
    'q4.button("Absent")': 'q4.button("Absent", key=f"quick_absent_{employee_id}_{day}")',
    'st.button("Save approved leave", type="primary")': 'st.button("Save approved leave", type="primary", key=f"save_leave_{employee_id}_{day}")',
}
for a, b in repls.items():
    s = s.replace(a, b)

p.write_text(s)
print('Patched calendar to move URL cell clicks into stable session_state before editing.')
