from pathlib import Path

path = Path(__file__).resolve().parents[1] / "api" / "server_review.py"
text = path.read_text(encoding="utf-8")

old_import = "from api.schedule_approved_leave import router as schedule_approved_leave_router"
new_import = "from api.schedule_approved_leave_v2 import router as schedule_approved_leave_router"
include_line = "app.include_router(schedule_approved_leave_router)"

text = text.replace(old_import, new_import)

if new_import not in text:
    anchor = "from api.schedule_leave_statuses import router as schedule_leave_statuses_router"
    if anchor not in text:
        raise RuntimeError("schedule leave-status router import anchor not found")
    text = text.replace(anchor, anchor + "\n" + new_import)

if include_line not in text:
    anchor = "app.include_router(schedule_leave_statuses_router)"
    if anchor not in text:
        raise RuntimeError("schedule leave-status router include anchor not found")
    text = text.replace(anchor, anchor + "\n" + include_line)

path.write_text(text, encoding="utf-8")
print("Corrected approved leave router activated.")
