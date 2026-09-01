from __future__ import annotations

from api.schedules import DayActualPayload


def test_manual_actual_payload_carries_exact_shift_id() -> None:
    payload = DayActualPayload(
        shift_id=1298,
        employee_id=13,
        shift_date="2026-08-17",
        actual_in="21:00",
        actual_out="07:01",
    )
    assert payload.shift_id == 1298
    assert payload.employee_id == 13
