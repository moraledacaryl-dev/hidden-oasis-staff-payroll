from pathlib import Path

path = Path(__file__).resolve().parents[1] / "api" / "server_review.py"
text = path.read_text(encoding="utf-8")

import_line = "from api.schedule_day_reset import router as schedule_day_reset_router"
include_line = "app.include_router(schedule_day_reset_router)"

if import_line not in text:
    anchor = "from api.schedule_leave_statuses import router as schedule_leave_statuses_router"
    if anchor not in text:
        raise RuntimeError("schedule leave-status import anchor not found")
    text = text.replace(anchor, anchor + "\n" + import_line)

if include_line not in text:
    anchor = "app.include_router(schedule_leave_statuses_router)"
    if anchor not in text:
        raise RuntimeError("schedule leave-status include anchor not found")
    text = text.replace(anchor, anchor + "\n" + include_line)

path.write_text(text, encoding="utf-8")
print("Schedule day reset router activated.")
