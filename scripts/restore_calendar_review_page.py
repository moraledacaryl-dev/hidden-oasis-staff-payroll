from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
s = APP.read_text()

imp = "from core.calendar_review import render_calendar_review\n"
if imp not in s:
    anchor = "from core.integration_operations import (\n"
    idx = s.find(anchor)
    if idx == -1:
        raise SystemExit("Could not find integration_operations import block.")
    end = s.find(")\n", idx)
    if end == -1:
        raise SystemExit("Could not find end of integration_operations import block.")
    end += 2
    s = s[:end] + imp + s[end:]

if '        "Calendar Review",' not in s:
    s = s.replace(
        '        "Schedules & Logs",\n        "Attendance Review",',
        '        "Schedules & Logs",\n        "Calendar Review",\n        "Attendance Review",',
        1,
    )

if '    "Calendar Review":' not in s:
    s = s.replace(
        '    "Schedules & Logs": ("Owner", "Manager", "Supervisor", "Reception", "Payroll Clerk"),\n'
        '    "Attendance Review":',
        '    "Schedules & Logs": ("Owner", "Manager", "Supervisor", "Reception", "Payroll Clerk"),\n'
        '    "Calendar Review": ("Owner", "Manager", "Supervisor", "Reception", "Payroll Clerk"),\n'
        '    "Attendance Review":',
        1,
    )

if 'elif page == "Calendar Review":' not in s:
    marker = 'elif page == "Attendance Review":'
    idx = s.find(marker)
    if idx == -1:
        raise SystemExit("Could not find Attendance Review route.")
    block = '''elif page == "Calendar Review":
    render_calendar_review(conn, current_user, audit)

'''
    s = s[:idx] + block + s[idx:]

APP.write_text(s)
print("Restored Calendar Review page wiring in app.py.")
