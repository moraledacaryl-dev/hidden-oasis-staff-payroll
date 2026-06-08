"""Basic local smoke test for the Staff/Payroll prototype.
Run with: python smoke_test.py
"""
from core.db import get_conn, init_db, fetchall
from core.integration_accounting import enqueue_employee_sync, export_outbox_zip
from core.integration_operations import enqueue_operations_snapshot, build_operations_snapshot_payload


def main():
    conn = get_conn(':memory:')
    init_db(conn)
    snapshot = build_operations_snapshot_payload(conn)
    assert snapshot['event_type'] == 'staff.operations.snapshot'
    ops_id = enqueue_operations_snapshot(conn)
    emp_id = enqueue_employee_sync(conn)
    rows = fetchall(conn, 'SELECT * FROM integration_outbox ORDER BY id')
    assert len(rows) == 2
    assert ops_id != emp_id
    payload_zip = export_outbox_zip(conn, 'All')
    assert len(payload_zip) > 1000
    print('Smoke test passed: database, Operations payload, employee sync, and ZIP export are working.')


if __name__ == '__main__':
    main()
