from __future__ import annotations

from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "core" / "calendar_review.py"

STYLE = '''

def _inject_calendar_card_css() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button {
            width: 100%;
            min-height: 104px;
            justify-content: flex-start;
            align-items: flex-start;
            text-align: left;
            white-space: pre-wrap;
            line-height: 1.32;
            border-radius: 16px;
            border: 1px solid #dfd5c8;
            background: linear-gradient(180deg, #fffdf8 0%, #f8f3eb 100%);
            color: #332d26;
            padding: 10px 12px;
            box-shadow: 0 2px 8px rgba(52, 44, 35, 0.05);
            transition: transform .08s ease, box-shadow .08s ease, border-color .08s ease;
            font-size: .82rem;
        }
        div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 14px rgba(52, 44, 35, 0.10);
            border-color: #bfae98;
            background: linear-gradient(180deg, #ffffff 0%, #fbf3e5 100%);
        }
        div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button:focus {
            box-shadow: 0 0 0 3px rgba(184, 140, 82, 0.22);
            border-color: #b88c52;
        }
        div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button[kind="primary"] {
            min-height: auto;
            text-align: center;
            justify-content: center;
        }
        .calendar-legend {
            border: 1px solid #e7dfd5;
            background: #fffaf2;
            border-radius: 16px;
            padding: 10px 12px;
            margin: 8px 0 12px;
            color: #584f45;
            font-size: .86rem;
        }
        .calendar-employee-card {
            min-height: 104px;
            border-radius: 16px;
            border: 1px solid #e4dbcf;
            background: #fffdf8;
            padding: 10px 12px;
            box-shadow: 0 2px 8px rgba(52, 44, 35, 0.04);
        }
        .calendar-employee-name { font-weight: 750; color: #2f2923; margin-bottom: 4px; }
        .calendar-employee-meta { color: #756b60; font-size: .75rem; line-height: 1.3; }
        .calendar-header-card {
            border-radius: 14px;
            border: 1px solid #e6dccc;
            background: #f8f2e9;
            padding: 8px 10px;
            min-height: 58px;
            font-weight: 750;
            color: #3f372f;
        }
        .calendar-header-holiday { color: #8a5b0a; font-size: .72rem; font-weight: 600; margin-top: 3px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not find expected block for: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    if "def _inject_calendar_card_css" not in text:
        text = text.replace("def _cell_label(day: date, cell: dict[str, Any], holiday: dict[str, Any] | None) -> str:\n", STYLE + "\ndef _cell_label(day: date, cell: dict[str, Any], holiday: dict[str, Any] | None) -> str:\n", 1)

    text = text.replace(
        '    st.markdown("**Legend:** 🟢 OK · 🟡 Needs checking · 🔵 Pending · 🔴 Absent/problem · 🟣 Leave · 🎌 Holiday · ⚪ Empty/rest")\n',
        '    _inject_calendar_card_css()\n    st.markdown("<div class=\'calendar-legend\'><b>Legend:</b> 🟢 OK · 🟡 Needs checking · 🔵 Pending · 🔴 Absent/problem · 🟣 Leave · 🎌 Holiday · ⚪ Empty/rest</div>", unsafe_allow_html=True)\n',
    )

    text = text.replace(
        '    header_cols[0].markdown("**Employee**")\n    for i, d in enumerate(days):\n        h = holidays.get(_iso(d))\n        header_cols[i + 1].markdown(f"**{d.strftime(\'%a %b %d\')}**" + (f"  🎌  \\\\n{h[\'name\']}" if h else ""))\n',
        '    header_cols[0].markdown("<div class=\'calendar-header-card\'>Employee</div>", unsafe_allow_html=True)\n    for i, d in enumerate(days):\n        h = holidays.get(_iso(d))\n        holiday_line = f"<div class=\'calendar-header-holiday\'>🎌 {h[\'name\']}</div>" if h else ""\n        header_cols[i + 1].markdown(f"<div class=\'calendar-header-card\'>{d.strftime(\'%a %b %d\')}{holiday_line}</div>", unsafe_allow_html=True)\n',
    )

    text = text.replace(
        '        cols[0].markdown(f"**{emp[\'full_name\']}**  \\\\n<small>{emp.get(\'employee_code\',\'\')} • {emp.get(\'department\',\'\')} • {emp.get(\'position\',\'\')}</small>", unsafe_allow_html=True)\n',
        '        cols[0].markdown(f"<div class=\'calendar-employee-card\'><div class=\'calendar-employee-name\'>{emp[\'full_name\']}</div><div class=\'calendar-employee-meta\'>{emp.get(\'employee_code\',\'\')}<br>{emp.get(\'department\',\'\')} • {emp.get(\'position\',\'\')}</div></div>", unsafe_allow_html=True)\n',
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Patched Calendar Review to keep card-like aesthetic while using clickable cells.")


if __name__ == "__main__":
    main()
