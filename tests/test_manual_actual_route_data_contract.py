from __future__ import annotations

from pathlib import Path


def test_legacy_history_actual_handler_is_not_registered_for_manual_schedule_writes() -> None:
    server = Path("api/server.py").read_text()
    assert "REVISION_CONTROLS_EXCLUDED_ROUTES" in server
    assert '(f"{API_PREFIX}/schedules/day/actual", "POST")' in server


def test_shift_aware_actual_handler_persists_scheduled_shift_id() -> None:
    schedules = Path("api/schedules.py").read_text()
    assert "SET scheduled_shift_id=?" in schedules
    assert "INSERT INTO time_logs(\n                    scheduled_shift_id," in schedules


def test_legacy_history_actual_handler_is_employee_day_level_only() -> None:
    history = Path("api/schedule_history_controls.py").read_text()
    assert "existing = fetch_time_log(conn, payload.employee_id, shift_date)" in history
    assert "payload.shift_id" not in history.split('def save_actual_history', 1)[1].split('@router.post', 1)[0]
