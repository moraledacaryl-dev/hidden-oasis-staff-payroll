import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_accounting_outbox_snapshot.py"
spec = importlib.util.spec_from_file_location("staff_accounting_outbox_snapshot", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


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


class StaffAccountingOutboxSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE integration_outbox (
              id INTEGER PRIMARY KEY, destination TEXT, external_source TEXT,
              event_type TEXT, external_id TEXT, payload_json TEXT, status TEXT
            );
        """)

    def tearDown(self):
        self.conn.close()

    def test_excludes_employee_sync_and_other_destinations_without_private_payload(self):
        add(self.conn, 1, "payroll.run.paid", status="Completed", body_revision=3)
        add(self.conn, 2, "cash_advance.repaid", status="Dead Letter", revision=2)
        add(self.conn, 3, "employee.sync")
        add(self.conn, 4, "payroll.run.paid", dest="operations")
        add(self.conn, 5, "payroll.run.paid", source="other_sender")
        self.conn.commit()
        report = module.export_staff_outbox(self.conn)
        self.assertEqual(report["source"], "staff")
        self.assertFalse(report["complete_for_window"])
        self.assertTrue(report["full_source_scan"])
        self.assertEqual(report["events"], [
            {"destination": "accounting", "event_type": "payroll.run.paid",
             "external_id": "staff-fixture:1", "source_revision": 3, "status": "Completed"},
            {"destination": "accounting", "event_type": "cash_advance.repaid",
             "external_id": "staff-fixture:2", "source_revision": 2, "status": "Dead Letter"},
        ])
        serialized = json.dumps(report)
        for private in ("PRIVATE PERSON", "PRIVATE BANK", "99999", "employee.sync"):
            self.assertNotIn(private, serialized)

    def test_outbox_snapshot_is_all_statuses_and_unpaginated(self):
        for n in range(1, 470):
            add(self.conn, n, "payroll.run.approved", status="Retry" if n % 2 else "Processing")
        report = module.export_staff_outbox(self.conn)
        self.assertEqual(len(report["events"]), 469)
        self.assertEqual(report["events"][0]["source_revision"], 1)
        self.assertEqual(report["events"][-1]["external_id"], "staff-fixture:469")

    def test_malformed_or_mismatched_outbox_fails_without_partial_export(self):
        add(self.conn, 1, "payroll.run.paid")
        self.conn.execute("UPDATE integration_outbox SET payload_json=? WHERE id=1", ("{invalid",))
        with self.assertRaisesRegex(ValueError, "Invalid Staff financial"):
            module.export_staff_outbox(self.conn)
        self.conn.execute("UPDATE integration_outbox SET payload_json=? WHERE id=1",
                          (json.dumps({"external_id": "wrong", "source_revision": 1}),))
        with self.assertRaisesRegex(ValueError, "disagree"):
            module.export_staff_outbox(self.conn)
        self.conn.execute("UPDATE integration_outbox SET payload_json=? WHERE id=1",
                          (json.dumps({"external_id": "staff-fixture:1", "source_revision": -1}),))
        with self.assertRaisesRegex(ValueError, "invalid source revision"):
            module.export_staff_outbox(self.conn)

    def test_private_file_is_restricted_not_overwritten_and_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            dest = folder / "export.json"
            report = {"events": []}
            module.write_private(dest, report)
            self.assertEqual(json.loads(dest.read_text()), report)
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                module.write_private(dest, {"events": [{"unexpected": True}]})
            self.assertEqual(json.loads(dest.read_text()), report)
            link = folder / "link.json"
            link.symlink_to(dest)
            with self.assertRaises(OSError):
                module.write_private(link, report)

    def test_cli_runs_read_only_from_existing_absolute_sqlite_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            db_file = folder / "staff.sqlite"
            with sqlite3.connect(db_file) as db:
                db.executescript("""
                    CREATE TABLE integration_outbox (
                      id INTEGER PRIMARY KEY, destination TEXT, external_source TEXT,
                      event_type TEXT, external_id TEXT, payload_json TEXT, status TEXT
                    )
                """)
                add(db, 1, "payroll.run.paid", status="Completed")
                db.commit()
            output = folder / "protected.json"
            self.assertEqual(module.main(["--db", str(db_file), "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["events"][0]["external_id"], "staff-fixture:1")
            with sqlite3.connect(db_file) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM integration_outbox").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
