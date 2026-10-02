from pathlib import Path

def test_recalculation_preserves_statutory_catchups():
    source=Path("api/payroll_recalculate.py").read_text()
    assert 'catchup_total(conn, run_id, employee_id)' in source
    assert 'other + statutory_catchup' in source

def test_payslip_renders_catchup_label_separately():
    source=Path("apps/web/components/EmployeePayslip.tsx").read_text()
    assert "statutory_catchups" in source
    assert "excluding benefit catch-ups" in source

def test_payroll_card_exposes_benefit_catchup_editor():
    source=Path("apps/web/components/EmployeePayrollCard.tsx").read_text()
    assert "BenefitCatchupEditor" in source

def test_benefits_ledger_exposes_outside_payment_control():
    source=Path("apps/web/app/payroll/benefits/page.tsx").read_text()
    assert "OutsideBenefitPayment" in source
    assert "Paid separately" in source
