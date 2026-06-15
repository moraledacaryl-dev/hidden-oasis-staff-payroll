from pathlib import Path

p = Path('core/calendar_review.py')
s = p.read_text()

start = s.find('    payload = st.session_state.get("calendar_cell_to_edit")\n')
end = s.find('    with st.expander("Direct selector fallback"):', start)
if start < 0 or end < 0:
    raise SystemExit('calendar block not found')

block = '''    payload = st.session_state.get("calendar_cell_to_edit")
    if payload:
        if hasattr(st, "dialog"):
            title_date = datetime.strptime(str(payload["date"]), "%Y-%m-%d").date()

            @st.dialog(f"Edit {title_date.strftime('%a, %b %d, %Y')}", width="large")
            def popup() -> None:
                live_payload = st.session_state.get("calendar_cell_to_edit") or payload
                live_date = datetime.strptime(str(live_payload["date"]), "%Y-%m-%d").date()
                live_employee_id = int(live_payload["employee_id"])
                st.info(f"Editing: {live_date.strftime('%a, %b %d, %Y')} | employee ID {live_employee_id}")
                _render_editor(conn, current_user, live_employee_id, live_date, audit_func)
                close_key = f"close_calendar_editor_{live_employee_id}_{_iso(live_date)}"
                if st.button("Close", key=close_key):
                    st.session_state.pop("calendar_cell_to_edit", None)
                    st.rerun()

            popup()
        else:
            live_date = datetime.strptime(str(payload["date"]), "%Y-%m-%d").date()
            live_employee_id = int(payload["employee_id"])
            st.markdown("---")
            st.info(f"Editing: {live_date.strftime('%a, %b %d, %Y')} | employee ID {live_employee_id}")
            _render_editor(conn, current_user, live_employee_id, live_date, audit_func)

'''

s = s[:start] + block + s[end:]
p.write_text(s)
print('patched calendar dialog to use live selected date')
