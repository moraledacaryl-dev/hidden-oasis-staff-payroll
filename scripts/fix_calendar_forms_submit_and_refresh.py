from pathlib import Path

p = Path('core/calendar_review.py')
s = p.read_text()

# Keep the week selector honest: it controls the displayed week, not the saved date.
s = s.replace(
'''    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    week_start = c1.date_input("Week start", value=date.today() - timedelta(days=date.today().weekday()))
    week_start = week_start - timedelta(days=week_start.weekday())
    week_end = week_start + timedelta(days=6)
''',
'''    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    default_week = date.today() - timedelta(days=date.today().weekday())
    anchor_text = st.session_state.get("calendar_week_anchor")
    try:
        anchor_date = datetime.strptime(str(anchor_text), "%Y-%m-%d").date() if anchor_text else default_week
    except Exception:
        anchor_date = default_week
    picked_week = c1.date_input(
        "Week shown",
        value=anchor_date,
        help="This controls the Monday-Sunday calendar shown below. The popup date is the actual save date.",
        key="calendar_week_picker",
    )
    week_start = picked_week - timedelta(days=picked_week.weekday())
    st.session_state["calendar_week_anchor"] = _iso(week_start)
    week_end = week_start + timedelta(days=6)
''',
1)

# Show save confirmation after rerun.
s = s.replace(
'''    if c4.button("Refresh"):
        st.rerun()
    employees, grid, holidays = _load_week(conn, week_start, week_end, department)
''',
'''    if c4.button("Refresh"):
        st.rerun()
    if st.session_state.get("calendar_last_save"):
        st.success(st.session_state.pop("calendar_last_save"))
    employees, grid, holidays = _load_week(conn, week_start, week_end, department)
''',
1)

# Clicking a date keeps that week anchored.
s = s.replace(
'''            if cols[i + 1].button(label, key=f"cal_card_{emp['id']}_{d_iso}", use_container_width=True):
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(emp["id"]), "date": d_iso}
                st.rerun()
''',
'''            if cols[i + 1].button(label, key=f"cal_card_{emp['id']}_{d_iso}", use_container_width=True):
                st.session_state["calendar_week_anchor"] = d_iso
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(emp["id"]), "date": d_iso}
                st.rerun()
''',
1)

# Streamlit buttons inside forms don't reliably submit. Use form_submit_button everywhere inside forms.
s = s.replace('if st.form_submit_button("Save schedule", type="primary"):', 'if st.form_submit_button("Save schedule", type="primary", use_container_width=True):', 1)
s = s.replace('if st.form_submit_button("Save actual / OT", type="primary"):', 'if st.form_submit_button("Save actual / OT", type="primary", use_container_width=True):', 1)
s = s.replace('if st.form_submit_button("Save holiday for this date", type="primary"):', 'if st.form_submit_button("Save holiday for this date", type="primary", use_container_width=True):', 1)

# After successful saves, close popup and force the calendar grid to reload on the saved week.
s = s.replace(
'''                st.session_state["calendar_cell_to_edit"] = {"employee_id": employee_id, "date": day}
                st.success("Schedule saved.")
                st.rerun()
''',
'''                st.session_state["calendar_week_anchor"] = day
                st.session_state.pop("calendar_cell_to_edit", None)
                st.session_state["calendar_last_save"] = f"Schedule saved for {day}."
                st.rerun()
''',
1)

s = s.replace(
'''                st.session_state["calendar_cell_to_edit"] = {"employee_id": employee_id, "date": day}
                st.success("Actual log saved.")
                st.rerun()
''',
'''                st.session_state["calendar_week_anchor"] = day
                st.session_state.pop("calendar_cell_to_edit", None)
                st.session_state["calendar_last_save"] = f"Actual log saved for {day}."
                st.rerun()
''',
1)

s = s.replace(
'''            _mark_leave(conn, employee_id, day, leave_name, current_user)
            st.success("Leave saved.")
            st.rerun()
''',
'''            _mark_leave(conn, employee_id, day, leave_name, current_user)
            st.session_state["calendar_week_anchor"] = day
            st.session_state.pop("calendar_cell_to_edit", None)
            st.session_state["calendar_last_save"] = f"Leave saved for {day}."
            st.rerun()
''',
1)

s = s.replace(
'''                    _save_holiday(conn, day, hname.strip(), htype, hnotes)
                    st.success("Holiday saved.")
                    st.rerun()
''',
'''                    _save_holiday(conn, day, hname.strip(), htype, hnotes)
                    st.session_state["calendar_week_anchor"] = day
                    st.session_state.pop("calendar_cell_to_edit", None)
                    st.session_state["calendar_last_save"] = f"Holiday saved for {day}."
                    st.rerun()
''',
1)

for old, msg in [
    ('st.success("Reviewed.")', 'Reviewed saved'),
    ('st.success("Rest day saved.")', 'Rest day saved'),
    ('st.success("Copied.")', 'Copied schedule to actual'),
    ('st.success("Absent saved.")', 'Absent saved'),
]:
    repl = f'''st.session_state["calendar_week_anchor"] = day
            st.session_state.pop("calendar_cell_to_edit", None)
            st.session_state["calendar_last_save"] = f"{msg} for {{day}}."'''
    s = s.replace(old, repl, 1)

# Direct selector should also anchor the chosen week.
s = s.replace(
'''            if st.button("Open editor"):
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(opts[emp_label]), "date": _iso(selected_date)}
                st.rerun()
''',
'''            if st.button("Open editor"):
                selected_iso = _iso(selected_date)
                st.session_state["calendar_week_anchor"] = selected_iso
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(opts[emp_label]), "date": selected_iso}
                st.rerun()
''',
1)

p.write_text(s)
print('Patched calendar form submit behavior, save refresh, and week/date clarity.')
