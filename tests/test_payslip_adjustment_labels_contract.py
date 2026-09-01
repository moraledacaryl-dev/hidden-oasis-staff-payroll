from pathlib import Path


def test_payslip_api_exposes_manual_adjustment_labels() -> None:
    source = Path("api/payslip_distribution.py").read_text(encoding="utf-8")
    assert "pia.additional_earning_note AS manual_earning_label" in source
    assert "pia.other_deduction_note AS manual_deduction_label" in source
    assert 'row["manual_earning_amount"]' in source
    assert 'row["manual_deduction_amount"]' in source


def test_payslip_renders_exact_manual_labels_separately_from_generic_totals() -> None:
    source = Path("apps/web/app/payslips/page.tsx").read_text(encoding="utf-8")
    assert "manualEarningLabel" in source
    assert "manualDeductionLabel" in source
    assert "otherEarningsRemainder" in source
    assert "otherDeductionsRemainder" in source
    assert "{manualEarningLabel}" in source
    assert "{manualDeductionLabel}" in source


def test_adjustment_editor_calls_field_a_payslip_label() -> None:
    source = Path("apps/web/components/PayrollAdjustmentEditor.tsx").read_text(encoding="utf-8")
    assert source.count("Payslip label") >= 2
    assert "This exact label will appear" in source
