from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header

import api.schedules as schedule_api
from api.schedule_validation import validate_break_minutes, validate_ot_hours, validate_positive_employee_id, validate_time

router = APIRouter(prefix="/api/v1")


def check_planned_shift(payload: Any) -> None:
    validate_positive_employee_id(getattr(payload, "employee_id", None))
    validate_time(getattr(payload, "start_time", None), "start_time")
    validate_time(getattr(payload, "end_time", None), "end_time")
    validate_break_minutes(getattr(payload, "break_minutes", 60))


@router.post("/schedules/shifts")
def create_validated_shift(payload: schedule_api.ShiftPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    check_planned_shift(payload)
    return schedule_api.create_shift(payload, authorization, x_api_key)


@router.post("/schedules/day/scheduled")
def save_validated_day_schedule(payload: schedule_api.DaySchedulePayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    check_planned_shift(payload)
    return schedule_api.save_day_schedule(payload, authorization, x_api_key)


@router.post("/schedules/day/actual")
def save_validated_day_actual(payload: schedule_api.DayActualPayload, authorization: str | None = Header(default=None, alias="Authorization"), x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    validate_positive_employee_id(payload.employee_id)
    validate_time(payload.actual_in, "actual_in")
    validate_time(payload.actual_out, "actual_out")
    validate_ot_hours(payload.approved_ot_hours)
    return schedule_api.save_day_actual(payload, authorization, x_api_key)
