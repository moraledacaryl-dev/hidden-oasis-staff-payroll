import importlib.util
import json
import os
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_accounting_outbox_snapshot.py"
spec = importlib.util.spec_from_file_location("staff_accounting_outbox_snapshot", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE integration_outbox (
          id INTEGER PRIMARY KEY, destination TEXT, external_source TEXT,
          event_type TEXT, external_id TEXT, payload_json TEXT, status TEXT
        );
    """)
    try:
        yield db
    finally:
        db.close()


def add(conn, n, event_type, *, dest="accounting", source="hidden_oasis_staff_payroll",
        status="Pending", revision=None, external_id=None, body_revision=None):
    ext = external_id or f"staff-fixture:{n}"
    envelope = {
        "external_id": ext,
        "source_record_type": "Employee",
        "employee_name": "PRIVATE PERSON DO NOT EXPORT",
        "payload": {
            "totals": {"net_pay": 99999},
            "financial_account": "PRIVATE BANK ACCOUNT",
        },
    }
    if revision is not None:
        envelope["source_revision"] = revision
    if body_revision is not None:
        envelope["payload"]["source_revision"] = body_revision
    conn.execute(
        "INSERT INTO integration_outbox VALUES (?, ?, ?, ?, ?, ?, ?)",
        (n, dest, source, event_type, ext, json.dumps(envelope), status),
    )


def test_excludes_employee_sync_and_other_destinations_without_private_payload(conn):
    add(conn, 1, "payroll.run.paid", status="Completed", body_revision=3)
    add(conn, 2, "cash_advance.repaid", status="Dead Letter", revision=2)
    add(conn, 3, "employee.sync")
    add(conn, 4, "payroll.run.paid", dest="operations")
    add(conn, 5, "payroll.run.paid", source="other_sender")
    conn.commit()
    report = module.export_staff_outbox(conn)
    assert report["source"] == "staff"
    assert report["complete_for_window"] is False
    assert report["full_source_scan"] is True
    assert report["events"] == [
        {"destination": "accounting", "event_type": "payroll.run.paid",
         "external_id": "staff-fixture:1", "source_revision": 3, "status": "Completed"},
        {"destination": "accounting", "event_type": "cash_advance.repaid",
         "external_id": "staff-fixture:2", "source_revision": 2, "status": "Dead Letter"},
    ]
    serialized = json.dumps(report)
    assert "PRIVATE PERSON" not in serialized
    assert "PRIVATE BANK" not in serialized
    assert "99999" not in serialized
    assert "employee.sync" not in serialized


def test_outbox_snapshot_is_all_statuses_and_unpaginated(conn):
    for n in range(1, 470):
        add(conn, n, "payroll.run.approved", status="Retry" if n % 2 else "Processing")
    report = module.export_staff_outbox(conn)
    assert len(report["events"]) == 469
    assert report["events"][0]["source_revision"] == 1
    assert report["events"][-1]["external_id"] == "staff-fixture:469"


def test_malformed_or_mismatched_outbox_fails_without_partial_export(conn):
    add(conn, 1, "payroll.run.paid")
    conn.execute("UPDATE integration_outbox SET payload_json=? WHERE id=1", ('{invalid',))
    with pytest.raises(ValueError, match="Invalid Staff financial"):
        module.export_staff_outbox(conn)
    conn.execute("UPDATE integration_outbox SET payload_json=? WHERE id=1",
                 (json.dumps({"external_id": "wrong", "source_revision": 1}),))
    with pytest.raises(ValueError, match="disagree"):
        module.export_staff_outbox(conn)
    conn.execute("UPDATE integration_outbox SET payload_json=? WHERE id=1",
                 (json.dumps({"external_id": "staff-fixture:1", "source_revision": -1}),))
    with pytest.raises(ValueError, match="invalid source revision"):
        module.export_staff_outbox(conn)


def test_private_file_is_restricted_not_overwritten_and_does_not_follow_symlinks(tmp_path):
    dest = tmp_path / "export.json"
    report = {"events": []}
    module.write_private(dest, report)
    assert json.loads(dest.read_text()) == report
    assert dest.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        module.write_private(dest, {"events": [{"unexpected": True}]})
    assert json.loads(dest.read_text()) == report
    link = tmp_path / "link.json"
    link.symlink_to(dest)
    with pytest.raises(OSError):
        module.write_private(link, report)


def test_cli_runs_read_only_from_existing_absolute_sqlite_file(tmp_path, capsys):
    db_file = tmp_path / "staff.sqlite"
    with sqlite3.connect(db_file) as db:
        db.executescript("""
           CREATE TABLE integration_outbox (
             id INTEGER PRIMARY KEY, destination TEXT, external_source TEXT,
             event_type TEXT, external_id TEXT, payload_json TEXT, status TEXT
           )
        """)
        add(db, 1, "payroll.run.paid", status="Completed")
        db.commit()
    output = tmp_path / "protected.json"
    assert module.main(["--db", str(db_file), "--output", str(output)]) == 0
    captured = capsys.readouterr().out
    assert "staff-fixture:1" not in captured
    assert "PRIVATE" not in captured
    assert "events=1" in captured
    assert json.loads(output.read_text())["events"][0]["external_id"] == "staff-fixture:1"
    with sqlite3.connect(db_file) as db:
        assert db.execute("SELECT COUNT(*) FROM integration_outbox").fetchone()[0] == 1
