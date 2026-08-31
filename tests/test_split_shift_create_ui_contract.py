from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_add_another_shift_does_not_hydrate_existing_employee_day_shift():
    source = (ROOT / "apps/web/components/ScheduleDayEditorModal.tsx").read_text(encoding="utf-8")

    assert "if (!shift?.id && selectedEmployeeId)" in source
    assert "params.set(\"employee_id\", String(selectedEmployeeId))" not in source
    assert "shift_id: currentShift?.id || null" in source
