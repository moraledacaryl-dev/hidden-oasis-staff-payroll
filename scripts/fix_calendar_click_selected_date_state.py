from pathlib import Path

CAL = Path(__file__).resolve().parents[1] / "core" / "calendar_review.py"
s = CAL.read_text()

old = '''    payload = st.session_state.get("calendar_cell_to_edit")
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
'''

new = '''    payload = st.session_state.get("calendar_cell_to_edit")
    if payload:
        selected_date = datetime.strptime(str(payload["date"]), "%Y-%m-%d").date()
        employee_id = int(payload["employee_id"])
        st.markdown("---")
        st.info(f"Editing selected calendar cell: {selected_date.strftime('%a, %b %d, %Y')} — employee ID {employee_id}")
        if st.button("Close calendar editor", key=f"close_calendar_editor_{employee_id}_{_iso(selected_date)}"):
            st.session_state.pop("calendar_cell_to_edit", None)
            st.rerun()
        _render_editor(conn, current_user, employee_id, selected_date, audit_func)
'''

if old not in s:
    raise SystemExit("Could not find old dialog-based calendar editor block. Stop and inspect core/calendar_review.py around payload = st.session_state.get(...).")

s = s.replace(old, new, 1)
CAL.write_text(s)
print("Replaced dialog calendar editor with inline selected-date editor.")
