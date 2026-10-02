from __future__ import annotations
import sqlite3
from api.statutory_settlements import ensure_statutory_settlement_schema, _obligation, _settled_amount, catchup_lines


def db():
    conn=sqlite3.connect(":memory:")
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
    CREATE TABLE employees(id INTEGER PRIMARY KEY, full_name TEXT);
    CREATE TABLE payroll_runs(id INTEGER PRIMARY KEY, status TEXT, superseded_by_run_id INTEGER);
    CREATE TABLE payroll_items(id INTEGER PRIMARY KEY, payroll_run_id INTEGER, employee_id INTEGER, other_deductions REAL, total_deductions REAL, net_pay REAL);
    CREATE TABLE payroll_statutory_months(id INTEGER PRIMARY KEY, payroll_run_id INTEGER, employee_id INTEGER, month_start TEXT, philhealth_ee REAL, pagibig_ee REAL);
    INSERT INTO employees VALUES(1,'Test Employee');
    """)
    ensure_statutory_settlement_schema(conn)
    return conn


def test_paid_snapshot_counts_as_settled_for_duplicate_protection():
    conn=db()
    conn.execute("INSERT INTO payroll_runs VALUES(1,'Paid',NULL)")
    conn.execute("INSERT INTO payroll_statutory_months VALUES(1,1,1,'2026-09-01',250,200)")
    assert _obligation(conn,1,"philhealth","2026-09-01")==250
    assert _settled_amount(conn,1,"philhealth","2026-09-01")==250


def test_unpaid_snapshot_is_due_but_not_yet_settled():
    conn=db()
    conn.execute("INSERT INTO payroll_runs VALUES(1,'Approved',NULL)")
    conn.execute("INSERT INTO payroll_statutory_months VALUES(1,1,1,'2026-09-01',250,200)")
    assert _obligation(conn,1,"pagibig","2026-09-01")==200
    assert _settled_amount(conn,1,"pagibig","2026-09-01")==0


def test_outside_payment_settles_month_without_payroll_run():
    conn=db()
    conn.execute("INSERT INTO payroll_runs VALUES(1,'Approved',NULL)")
    conn.execute("INSERT INTO payroll_statutory_months VALUES(1,1,1,'2026-09-01',250,200)")
    conn.execute("""INSERT INTO statutory_employee_settlements(employee_id,program,contribution_month,amount,collection_method,payment_date,created_at,updated_at) VALUES(1,'philhealth','2026-09-01',250,'outside_payment','2026-10-01','x','x')""")
    assert _settled_amount(conn,1,"philhealth","2026-09-01")==250


def test_catchup_label_names_program_and_contribution_month():
    conn=db()
    conn.execute("INSERT INTO payroll_runs VALUES(2,'Draft',NULL)")
    conn.execute("INSERT INTO payroll_items VALUES(2,2,1,250,250,1000)")
    conn.execute("""INSERT INTO statutory_employee_settlements(employee_id,program,contribution_month,amount,collection_method,payroll_run_id,created_at,updated_at) VALUES(1,'philhealth','2026-09-01',250,'payroll_catchup',2,'x','x')""")
    lines=catchup_lines(conn,2,1)
    assert lines[0]["label"]=="PhilHealth — 2026-09 catch-up"
