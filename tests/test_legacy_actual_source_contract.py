from pathlib import Path


def test_legacy_actual_handler_contains_no_direct_time_log_write() -> None:
    source = Path("api/schedule_history_controls.py").read_text()
    block = source.split('def save_actual_history', 1)[1].split('@router.post("/schedules/shifts/{shift_id}/move")', 1)[0]
    assert "canonical_save_day_actual(payload, authorization, x_api_key)" in block
    assert "UPDATE time_logs" not in block
    assert "INSERT INTO time_logs" not in block
