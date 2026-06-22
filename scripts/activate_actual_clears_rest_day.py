from pathlib import Path

path = Path(__file__).resolve().parents[1] / "api" / "schedules.py"
text = path.read_text(encoding="utf-8")

actual_anchor = '''        timestamp = now_iso()
        shift = fetch_shift(conn, None, payload.employee_id, shift_date)
'''
actual_replacement = '''        timestamp = now_iso()
        conn.execute(
            """
            UPDATE schedule_day_markers
            SET active=0, updated_by=?, updated_at=?
            WHERE employee_id=? AND date(work_date)=date(?) AND marker_type='Rest Day'
            """,
            (user.get("display_name"), timestamp, payload.employee_id, shift_date),
        )
        shift = fetch_shift(conn, None, payload.employee_id, shift_date)
'''

schedule_anchor = '''        timestamp = now_iso()
        before = schedule_row(conn, payload.shift_id) if payload.shift_id else None
'''
schedule_replacement = '''        timestamp = now_iso()
        if employee_id:
            conn.execute(
                """
                UPDATE schedule_day_markers
                SET active=0, updated_by=?, updated_at=?
                WHERE employee_id=? AND date(work_date)=date(?) AND marker_type='Rest Day'
                """,
                (user.get("display_name"), timestamp, employee_id, payload.shift_date.isoformat()),
            )
        before = schedule_row(conn, payload.shift_id) if payload.shift_id else None
'''

changed = False
if actual_replacement not in text:
    if actual_anchor not in text:
        raise RuntimeError("save_day_actual anchor not found")
    text = text.replace(actual_anchor, actual_replacement, 1)
    changed = True

if schedule_replacement not in text:
    if schedule_anchor not in text:
        raise RuntimeError("save_day_schedule anchor not found")
    text = text.replace(schedule_anchor, schedule_replacement, 1)
    changed = True

path.write_text(text, encoding="utf-8")
print("Actual and scheduled saves now clear Rest Day markers." if changed else "Rest Day clearing already active.")
