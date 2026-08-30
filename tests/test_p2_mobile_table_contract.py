from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_mobile_record_styles_are_loaded_globally():
    layout = read("apps/web/app/layout.tsx")
    assert 'import "./p2-mobile-records.css";' in layout


def test_settings_users_become_labeled_mobile_records():
    css = read("apps/web/app/p2-mobile-records.css")
    source = read("apps/web/components/UserManagementClient.tsx")

    assert ".user-table thead" in css
    assert '.user-table td:nth-child(1)::before { content: "User"; }' in css
    assert '.user-table td:nth-child(2)::before { content: "Role"; }' in css
    assert '.user-table td:nth-child(3)::before { content: "Employee"; }' in css
    assert '.user-table td:nth-child(8)::before' in css
    assert "grid-template-columns: 1fr;" in css
    assert 'aria-label={`Role for ${user.display_name}`}' in source
    assert 'aria-label={`Employee linked to ${user.display_name}`}' in source


def test_cash_advance_audit_becomes_labeled_mobile_records():
    css = read("apps/web/app/p2-mobile-records.css")
    payroll = read("apps/web/app/payroll/runs/[id]/page.tsx")

    assert ".cash-advance-table thead" in css
    assert '.cash-advance-table td:nth-child(4)::before { content: "Balance before"; }' in css
    assert '.cash-advance-table td:nth-child(5)::before { content: "Expected"; }' in css
    assert '.cash-advance-table td:nth-child(6)::before { content: "Applied"; }' in css
    assert '.cash-advance-table td:nth-child(7)::before { content: "Balance after"; }' in css
    assert 'className="cash-advance-table"' in payroll
    assert 'className="cash-advance-table-wrap"' in payroll


def test_attendance_tables_have_explicit_mobile_scroll_affordance():
    css = read("apps/web/app/attendance/page.module.css")
    page = read("apps/web/app/attendance/page.tsx")

    assert ".tableWrap table{min-width:1180px}" in css
    assert ".tableWrap,.page :global(.table-wrap){position:relative;overflow-x:auto" in css
    assert "overscroll-behavior-inline:contain" in css
    assert "scrollbar-gutter:stable" in css
    assert ".tableWrap::before,.page :global(.table-wrap)::before" in css
    assert 'Swipe or scroll horizontally to view all columns' in css
    assert 'className="compliance-table"' in page
    assert 'title="Memo history"' in page
