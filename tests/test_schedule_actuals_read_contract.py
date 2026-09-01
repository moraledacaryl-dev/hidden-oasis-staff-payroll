from pathlib import Path


def test_weekly_actual_read_is_side_effect_free() -> None:
    source = Path("api/schedule_actuals.py").read_text()
    assert "reconcile_unlinked_split_shift_logs" not in source
    assert 'FROM time_logs tl' in source
    assert '"logs_linked": 0' in source


def test_schedule_page_maps_actuals_by_exact_shift_id() -> None:
    source = Path("apps/web/app/schedule/page.tsx").read_text()
    assert "actualsByShiftId" in source
    assert "actual.scheduled_shift_id" in source
    assert "shiftActualKey(item.id)" in source
