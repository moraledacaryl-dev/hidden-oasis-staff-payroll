from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_saved_actual_is_merged_back_into_schedule_card_state():
    source = (ROOT / "apps/web/components/ScheduleBoardClient.tsx").read_text(encoding="utf-8")

    assert "const savedShift: ScheduleShift = data.actual" in source
    assert "actual_in: data.actual.actual_in || null" in source
    assert "actual_out: data.actual.actual_out || null" in source
    assert "actual_status: data.actual.attendance_status || null" in source
    assert "approved_ot_hours: data.actual.approved_ot_hours || 0" in source
    assert "return [...withoutSaved, savedShift];" in source
