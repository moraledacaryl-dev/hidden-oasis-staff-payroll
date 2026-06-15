from __future__ import annotations

from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "core" / "calendar_review.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not find expected block for: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    old_time = '''def _time_text(value: Any) -> str:\n    if value is None:\n        return ""\n    text = str(value).strip()\n    if not text:\n        return ""\n    for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S"):\n        try:\n            return datetime.strptime(text, fmt).strftime("%I:%M %p").lstrip("0")\n        except Exception:\n            pass\n    return text\n'''
    new_time = '''def _time_text(value: Any) -> str:\n    if value is None:\n        return ""\n    text = str(value).strip()\n    if not text:\n        return ""\n    for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S"):\n        try:\n            return datetime.strptime(text, fmt).strftime("%-I:%M%p").lower().replace("m", "")\n        except Exception:\n            pass\n    return text\n'''
    text = replace_once(text, old_time, new_time, "compact time text")

    old_label = '''def _cell_label(day: date, cell: dict[str, Any], holiday: dict[str, Any] | None) -> str:\n    schedule = cell.get("schedule")\n    log = cell.get("log")\n    label, icon, _kind = _status_badge(cell, holiday)\n    lines = [f"{icon} {day.strftime('%a %d')}", label]\n    if holiday:\n        lines.append(f"Holiday: {holiday['name']}")\n    if schedule:\n        if int(schedule.get("is_rest_day") or 0):\n            lines.append("Sched: Rest day")\n        else:\n            lines.append(f"S: {_time_text(schedule.get('shift_start'))}-{_time_text(schedule.get('shift_end'))}")\n    else:\n        lines.append("S: —")\n    if log:\n        if int(log.get("is_absent") or 0):\n            lines.append(f"A: {log.get('absence_type') or 'Absent'}")\n        else:\n            lines.append(f"A: {_time_text(log.get('actual_in'))}-{_time_text(log.get('actual_out')) or '—'}")\n    else:\n        lines.append("A: —")\n    return "\\n".join(lines)\n'''
    new_label = '''def _short_label(label: str) -> str:\n    mapping = {\n        "Missing out": "Missing out",\n        "No log": "No log",\n        "Pending": "Pending",\n        "Needs Manager": "Needs mgr",\n        "Disputed": "Disputed",\n        "Absent": "Absent",\n        "Service Incentive Leave": "SIL",\n        "Sick Leave": "Sick",\n        "Bereavement Leave": "BL",\n        "Regular": "Regular hol",\n        "Special": "Special hol",\n    }\n    return mapping.get(label, label[:11])\n\n\ndef _cell_label(day: date, cell: dict[str, Any], holiday: dict[str, Any] | None) -> str:\n    schedule = cell.get("schedule")\n    log = cell.get("log")\n    label, icon, _kind = _status_badge(cell, holiday)\n    if schedule and int(schedule.get("is_rest_day") or 0):\n        s_line = "S Rest"\n    elif schedule:\n        s_line = f"S {_time_text(schedule.get('shift_start'))}-{_time_text(schedule.get('shift_end'))}"\n    else:\n        s_line = "S —"\n    if log and int(log.get("is_absent") or 0):\n        a_line = f"A {_short_label(str(log.get('absence_type') or 'Absent'))}"\n    elif log:\n        a_line = f"A {_time_text(log.get('actual_in'))}-{_time_text(log.get('actual_out')) or '—'}"\n    else:\n        a_line = "A —"\n    h_flag = " 🎌" if holiday else ""\n    return f"{icon}{h_flag} {day.strftime('%a %d')}\\n{_short_label(label)}\\n{s_line}\\n{a_line}"\n'''
    text = replace_once(text, old_label, new_label, "compact four-line cell labels")

    start = text.find("def _inject_calendar_card_css() -> None:")
    if start != -1:
        next_def = text.find("\ndef _short_label", start)
        if next_def == -1:
            next_def = text.find("\ndef _cell_label", start)
        if next_def != -1:
            replacement = r'''
def _inject_calendar_card_css() -> None:
    st.markdown(
        """
        <style>
        .calendar-legend {
            border: 1px solid #e7dfd5;
            background: #fffaf2;
            border-radius: 16px;
            padding: 10px 12px;
            margin: 8px 0 12px;
            color: #584f45;
            font-size: .86rem;
        }
        .calendar-employee-card,
        .calendar-cell-spacer,
        div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button {
            height: 104px !important;
            min-height: 104px !important;
            max-height: 104px !important;
            box-sizing: border-box !important;
        }
        div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button {
            width: 100% !important;
            display: flex !important;
            justify-content: flex-start !important;
            align-items: flex-start !important;
            text-align: left !important;
            white-space: pre-line !important;
            line-height: 1.18 !important;
            border-radius: 14px !important;
            border: 1px solid #ded8d0 !important;
            background: #fffdf8 !important;
            color: #332d26 !important;
            padding: 9px 10px !important;
            box-shadow: none !important;
            overflow: hidden !important;
            font-size: 0.76rem !important;
            font-weight: 600 !important;
        }
        div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button p {
            margin: 0 !important;
            padding: 0 !important;
            max-height: 84px !important;
            overflow: hidden !important;
        }
        div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button:hover {
            border-color: #bfae98 !important;
            background: #fff8ee !important;
            transform: none !important;
            box-shadow: 0 3px 8px rgba(52, 44, 35, 0.08) !important;
        }
        .calendar-employee-card {
            border-radius: 16px;
            border: 1px solid #e4dbcf;
            background: #fffdf8;
            padding: 13px 14px;
            overflow: hidden;
        }
        .calendar-employee-name { font-weight: 750; color: #2f2923; margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .calendar-employee-meta { color: #756b60; font-size: .72rem; line-height: 1.25; }
        .calendar-header-card {
            border-radius: 14px;
            border: 1px solid #e6dccc;
            background: #f8f2e9;
            padding: 10px 12px;
            height: 62px;
            box-sizing: border-box;
            font-weight: 750;
            color: #3f372f;
            overflow: hidden;
        }
        .calendar-header-holiday { color: #8a5b0a; font-size: .68rem; font-weight: 600; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        </style>
        """,
        unsafe_allow_html=True,
    )
'''
            text = text[:start] + replacement + text[next_def:]

    # Replace employee card only if previous patch did not fully compact it.
    text = text.replace(
        '<div class=\'calendar-employee-card\'><div class=\'calendar-employee-name\'>{emp[\'full_name\']}</div><div class=\'calendar-employee-meta\'>{emp.get(\'employee_code\',\'\')}<br>{emp.get(\'department\',\'\')} • {emp.get(\'position\',\'\')}</div></div>',
        '<div class=\'calendar-employee-card\'><div class=\'calendar-employee-name\'>{emp[\'full_name\']}</div><div class=\'calendar-employee-meta\'>{emp.get(\'employee_code\',\'\')}<br>{emp.get(\'department\',\'\')} • {emp.get(\'position\',\'\')}</div></div>'
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Patched Calendar Review to use a uniform compact clickable grid.")


if __name__ == "__main__":
    main()
