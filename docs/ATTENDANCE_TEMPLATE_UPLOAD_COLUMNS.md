# Attendance Template Columns

Required columns:

work_date, employee_name, biometric_id, time_in, time_out, time_out_date, break_minutes, attendance_status, remarks, is_absent, is_halfday, is_ot, ot_hours, ot_reason, needs_review, review_note

Notes:

- Use one row per employee per work date.
- Use YYYY-MM-DD dates when possible.
- Use AM/PM or 24-hour time.
- For overnight duty, set time_out_date to the next calendar date.
- Use needs_review = 1 for unclear rows.
