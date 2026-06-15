from __future__ import annotations

from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not find expected block for: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    if "from core.calendar_review import render_calendar_review" not in text:
        text = replace_once(
            text,
            "from core.reviews import build_annual_review_auto_summary\n",
            "from core.reviews import build_annual_review_auto_summary\nfrom core.calendar_review import render_calendar_review\n",
            "calendar review import",
        )

    if '"Calendar Review",' not in text:
        text = replace_once(
            text,
            '        "Schedules & Logs",\n',
            '        "Schedules & Logs",\n        "Calendar Review",\n',
            "sidebar calendar page",
        )
        text = replace_once(
            text,
            '    "Schedules & Logs": ("Owner", "Manager", "Supervisor", "Reception", "Payroll Clerk"),\n',
            '    "Schedules & Logs": ("Owner", "Manager", "Supervisor", "Reception", "Payroll Clerk"),\n    "Calendar Review": ("Owner", "Manager", "Supervisor", "Reception", "Payroll Clerk"),\n',
            "calendar page roles",
        )

    if 'elif page == "Calendar Review":' not in text:
        text = replace_once(
            text,
            'elif page == "Attendance Review":\n',
            'elif page == "Calendar Review":\n    render_calendar_review(conn, current_user, audit)\n\nelif page == "Attendance Review":\n',
            "calendar review branch",
        )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Patched app.py to enable Calendar Review.")


if __name__ == "__main__":
    main()
