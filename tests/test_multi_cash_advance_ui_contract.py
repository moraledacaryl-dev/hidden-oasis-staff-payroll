from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / "apps/web/components/PayrollAdjustmentEditor.tsx").read_text()
SERVER = (ROOT / "api/server.py").read_text()
AGGREGATE = (ROOT / "api/payroll_adjustments_aggregate.py").read_text()


def test_editor_uses_employee_level_cash_advance_amount() -> None:
    assert "Select the exact advance" not in EDITOR
    assert "automatically applied to eligible advances oldest first" in EDITOR
    assert 'cash_advance_id: null' in EDITOR
    assert "cash_advance_total_available" in EDITOR
    assert "How this deduction will be applied" in EDITOR


def test_server_routes_adjustments_to_aggregate_allocator() -> None:
    assert "from api.payroll_adjustments_aggregate import router as payroll_adjustments_router" in SERVER


def test_aggregate_save_clears_legacy_exact_advance_binding() -> None:
    assert "cash_advance_id=NULL" in AGGREGATE
    assert "employee's available cash-advance balance" in AGGREGATE
    assert "_other_draft_reserved_total" in AGGREGATE
