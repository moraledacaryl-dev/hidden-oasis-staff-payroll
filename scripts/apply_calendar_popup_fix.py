from pathlib import Path

p = Path('core/calendar_review.py')
s = p.read_text()
start = s.find('    payload = st.session_state.get("calendar_cell_to_edit")\n')
end = s.find('    with st.expander("Direct selector fallback"):', start)
if start < 0 or end < 0:
    raise SystemExit('calendar block not found')

block = '''    payload = st.session_state.get("calendar_cell_to_edit")
    if payload:
        selected_date = datetime.strptime(str(payload["date"]), "%Y-%m-%d").date()
        employee_id = int(payload["employee_id"])
        title = "Edit " + selected_date.strftime("%a, %b %d, %Y")
        if hasattr(st, "dialog"):
            @st.dialog(title, width="large")
            def popup() -> None:
                st.info("Editing: " + selected_date.strftime("%a, %b %d, %Y") + " | employee ID " + str(employee_id))
                _render_editor(conn, current_user, employee_id, selected_date, audit_func)
                close_key = "close_calendar_editor_" + str(employee_id) + "_" + _iso(selected_date)
                if st.button("Close", key=close_key):
                    del st.session_state["calendar_cell_to_edit"]
                    st.rerun()
            popup()
        else:
            st.markdown("---")
            st.info("Editing: " + selected_date.strftime("%a, %b %d, %Y") + " | employee ID " + str(employee_id))
            _render_editor(conn, current_user, employee_id, selected_date, audit_func)

'''

p.write_text(s[:start] + block + s[end:])
print('calendar popup restored')
