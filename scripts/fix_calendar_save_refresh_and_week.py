from pathlib import Path

p = Path('core/calendar_review.py')
s = p.read_text()

old = '''    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    week_start = c1.date_input("Week start", value=date.today() - timedelta(days=date.today().weekday()))
    week_start = week_start - timedelta(days=week_start.weekday())
    week_end = week_start + timedelta(days=6)
'''
new = '''    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    default_week = date.today() - timedelta(days=date.today().weekday())
    anchor_text = st.session_state.get("calendar_week_anchor")
    try:
        anchor_date = datetime.strptime(str(anchor_text), "%Y-%m-%d").date() if anchor_text else default_week
    except Exception:
        anchor_date = default_week
    picked_week = c1.date_input(
        "Week shown",
        value=anchor_date,
        help="This selector chooses the week shown below. It normalizes to Monday-Sunday. The popup save date is the date shown inside the popup.",
    )
    week_start = picked_week - timedelta(days=picked_week.weekday())
    st.session_state["calendar_week_anchor"] = _iso(week_start)
    week_end = week_start + timedelta(days=6)
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    print('week selector block already changed or not found')

old = '''    if c4.button("Refresh"):
        st.rerun()
    employees, grid, holidays = _load_week(conn, week_start, week_end, department)
'''
new = '''    if c4.button("Refresh"):
        st.rerun()
    if st.session_state.get("calendar_last_save"):
        st.success(st.session_state.pop("calendar_last_save"))
    employees, grid, holidays = _load_week(conn, week_start, week_end, department)
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    print('refresh/last-save insertion block already changed or not found')

old = '''            if cols[i + 1].button(label, key=f"cal_card_{emp['id']}_{d_iso}", use_container_width=True):
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(emp["id"]), "date": d_iso}
                st.rerun()
'''
new = '''            if cols[i + 1].button(label, key=f"cal_card_{emp['id']}_{d_iso}", use_container_width=True):
                st.session_state["calendar_week_anchor"] = d_iso
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(emp["id"]), "date": d_iso}
                st.rerun()
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    print('calendar card click block already changed or not found')

old = '''                st.session_state["calendar_cell_to_edit"] = {"employee_id": employee_id, "date": day}
                st.success("Schedule saved.")
                st.rerun()
'''
new = '''                st.session_state["calendar_week_anchor"] = day
                st.session_state.pop("calendar_cell_to_edit", None)
                st.session_state["calendar_last_save"] = f"Schedule saved for {day}."
                st.rerun()
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    print('schedule save rerun block already changed or not found')

old = '''                st.session_state["calendar_cell_to_edit"] = {"employee_id": employee_id, "date": day}
                st.success("Actual log saved.")
                st.rerun()
'''
new = '''                st.session_state["calendar_week_anchor"] = day
                st.session_state.pop("calendar_cell_to_edit", None)
                st.session_state["calendar_last_save"] = f"Actual log saved for {day}."
                st.rerun()
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    print('actual save rerun block already changed or not found')

old = '''            _mark_leave(conn, employee_id, day, leave_name, current_user)
            st.success("Leave saved.")
            st.rerun()
'''
new = '''            _mark_leave(conn, employee_id, day, leave_name, current_user)
            st.session_state["calendar_week_anchor"] = day
            st.session_state.pop("calendar_cell_to_edit", None)
            st.session_state["calendar_last_save"] = f"Leave saved for {day}."
            st.rerun()
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    print('leave save rerun block already changed or not found')

old = '''                    _save_holiday(conn, day, hname.strip(), htype, hnotes)
                    st.success("Holiday saved.")
                    st.rerun()
'''
new = '''                    _save_holiday(conn, day, hname.strip(), htype, hnotes)
                    st.session_state["calendar_week_anchor"] = day
                    st.session_state.pop("calendar_cell_to_edit", None)
                    st.session_state["calendar_last_save"] = f"Holiday saved for {day}."
                    st.rerun()
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    print('holiday save rerun block already changed or not found')

quick_repls = {
'''            st.success("Reviewed.")
            st.rerun()
''': '''            st.session_state["calendar_week_anchor"] = day
            st.session_state.pop("calendar_cell_to_edit", None)
            st.session_state["calendar_last_save"] = f"Reviewed saved for {day}."
            st.rerun()
''',
'''            st.success("Rest day saved.")
            st.rerun()
''': '''            st.session_state["calendar_week_anchor"] = day
            st.session_state.pop("calendar_cell_to_edit", None)
            st.session_state["calendar_last_save"] = f"Rest day saved for {day}."
            st.rerun()
''',
'''            st.success("Copied.")
            st.rerun()
''': '''            st.session_state["calendar_week_anchor"] = day
            st.session_state.pop("calendar_cell_to_edit", None)
            st.session_state["calendar_last_save"] = f"Copied schedule to actual for {day}."
            st.rerun()
''',
'''            st.success("Absent saved.")
            st.rerun()
''': '''            st.session_state["calendar_week_anchor"] = day
            st.session_state.pop("calendar_cell_to_edit", None)
            st.session_state["calendar_last_save"] = f"Absent saved for {day}."
            st.rerun()
''',
}
for old, new in quick_repls.items():
    if old in s:
        s = s.replace(old, new, 1)

old = '''            if st.button("Open editor"):
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(opts[emp_label]), "date": _iso(selected_date)}
                st.rerun()
'''
new = '''            if st.button("Open editor"):
                selected_iso = _iso(selected_date)
                st.session_state["calendar_week_anchor"] = selected_iso
                st.session_state["calendar_cell_to_edit"] = {"employee_id": int(opts[emp_label]), "date": selected_iso}
                st.rerun()
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    print('direct selector open block already changed or not found')

p.write_text(s)
print('Patched calendar save refresh behavior and week/date clarity.')
