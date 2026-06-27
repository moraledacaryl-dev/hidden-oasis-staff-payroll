from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def validate_time(value: str | None, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not TIME_PATTERN.fullmatch(text):
        raise HTTPException(status_code=422, detail=f"{field_name} must use HH:MM 24-hour time.")
    return text


def validate_break_minutes(value: Any, field_name: str = "break_minutes") -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be a number of minutes.") from exc
    if minutes < 0 or minutes > 720:
        raise HTTPException(status_code=422, detail=f"{field_name} must be between 0 and 720 minutes.")
    return minutes


def validate_positive_employee_id(value: int | None) -> int | None:
    if value is None:
        return None
    try:
        employee_id = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="employee_id must be a positive number.") from exc
    if employee_id <= 0:
        raise HTTPException(status_code=422, detail="employee_id must be positive when provided.")
    return employee_id


def validate_ot_hours(value: Any, field_name: str = "approved_ot_hours") -> float:
    try:
        hours = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be a number of hours.") from exc
    if hours < 0 or hours > 24:
        raise HTTPException(status_code=422, detail=f"{field_name} must be between 0 and 24 hours.")
    return hours


def validate_day_editor_leave_fraction(leave_days: Any = None, leave_hours: Any = None, scheduled_paid_hours: float | None = None) -> float:
    days: float | None = None
    hours: float | None = None
    if leave_hours not in (None, ""):
        try:
            hours = float(leave_hours)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="leave_hours must be numeric.") from exc
        if hours < 0 or hours > 24:
            raise HTTPException(status_code=422, detail="leave_hours must be between 0 and 24.")
    if hours is not None and hours > 0:
        base_hours = scheduled_paid_hours if scheduled_paid_hours and scheduled_paid_hours > 0 else 8.0
        days = hours / base_hours
    elif leave_days not in (None, ""):
        try:
            days = float(leave_days)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="leave_days must be numeric.") from exc
    if days is None:
        days = 1.0
    if days <= 0 or days > 1:
        raise HTTPException(status_code=422, detail="Day editor leave must be greater than 0 and no more than 1 day.")
    return round(days, 4)
