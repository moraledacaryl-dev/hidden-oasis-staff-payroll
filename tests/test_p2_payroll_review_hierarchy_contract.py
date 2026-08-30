from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_adjustment_editor_uses_focus_safe_drawer_and_named_modes():
    source = read("apps/web/components/PayrollAdjustmentEditor.tsx")

    assert 'import { AppDrawer } from "@/components/AppSurface";' in source
    assert "<AppDrawer" in source
    assert 'role="tablist"' in source
    assert 'aria-label="Adjustment type"' in source
    assert ">Cash advance<" in source
    assert ">Additional earning<" in source
    assert ">Other deduction<" in source
    assert "Apply cash advance / adjust pay" not in source


def test_adjustment_editor_previews_net_effect_before_save():
    source = read("apps/web/components/PayrollAdjustmentEditor.tsx")
    card = read("apps/web/components/EmployeePayrollCard.tsx")

    assert "currentNetPay" in source
    assert "projectedNetPay" in source
    assert "projectedDelta" in source
    assert 'aria-live="polite"' in source
    assert "savedAdditional" in source
    assert "savedOtherDeduction" in source
    assert "savedCash" in source
    assert "currentNetPay={Number(item.net_pay || 0)}" in card
    assert "The payslip preview updates after saving" not in card


def test_adjustment_save_keeps_complete_audited_payload_and_version_guard():
    source = read("apps/web/components/PayrollAdjustmentEditor.tsx")

    assert "additional_earning: additionalEarning" in source
    assert "other_deduction: otherDeduction" in source
    assert "cash_advance_id: selectedAdvanceId" in source
    assert "cash_advance_amount: cashAmount" in source
    assert "expected_version: Number(adjustment.version ?? 0)" in source
    assert "if (response.status === 409) void load();" in source


def test_revision_tools_are_collapsed_without_source_changes():
    source = read("apps/web/components/PayrollRevisionBanner.tsx")
    layout = read("apps/web/app/layout.tsx")
    css = read("apps/web/app/payroll/runs/[id]/payroll-review-hierarchy.css")

    assert "useState(Boolean(delta.changed))" in source
    assert 'aria-expanded={toolsOpen}' in source
    assert "setToolsOpen" in source
    assert "Revision tools" in source
    assert 'import "./payroll/runs/[id]/payroll-review-hierarchy.css";' in layout
    assert ".payroll-revision-toggle" in css
    assert ".payroll-revision-body" in css
