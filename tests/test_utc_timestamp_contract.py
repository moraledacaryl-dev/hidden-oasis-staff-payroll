from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import core.db as db
from core.login_security import lock_remaining_seconds, record_login_failure
from core.observability import (
    business_today,
    parse_timestamp_utc,
    utc_iso,
    utc_storage_iso,
)


ROOT = Path(__file__).resolve().parents[1]


class UtcTimestampContractTests(unittest.TestCase):
    def test_database_clock_writes_explicit_utc_offset(self) -> None:
        value = db.now_iso()
        parsed = datetime.fromisoformat(value)
        self.assertEqual(parsed.utcoffset(), timedelta(0))
        self.assertTrue(value.endswith("+00:00"))

    def test_storage_format_preserves_legacy_text_ordering(self) -> None:
        current = utc_storage_iso(datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc))
        self.assertLess("2026-08-30 14:59:59", current)
        self.assertGreater("2026-08-30 15:00:01", current)
        self.assertLess(
            current,
            utc_storage_iso(datetime(2026, 8, 30, 15, 0, 1, tzinfo=timezone.utc)),
        )

    def test_api_iso_has_z_and_parser_accepts_legacy_naive(self) -> None:
        self.assertEqual(
            utc_iso(datetime(2026, 8, 30, 15, 30, tzinfo=timezone(timedelta(hours=8)))),
            "2026-08-30T07:30:00Z",
        )
        parsed = parse_timestamp_utc("2026-08-30 07:30:00")
        self.assertEqual(parsed, datetime(2026, 8, 30, 7, 30, tzinfo=timezone.utc))

    def test_business_date_uses_asia_manila_boundary(self) -> None:
        before_midnight_utc = datetime(2026, 8, 30, 15, 59, 59, tzinfo=timezone.utc)
        after_midnight_utc = datetime(2026, 8, 30, 16, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(str(business_today(before_midnight_utc)), "2026-08-30")
        self.assertEqual(str(business_today(after_midnight_utc)), "2026-08-31")

    def test_login_lock_reads_legacy_and_writes_aware_utc(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE login_attempts (
                identifier TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                failed_count INTEGER NOT NULL DEFAULT 0,
                last_failed_at TEXT,
                locked_until TEXT,
                PRIMARY KEY(identifier, ip_address)
            )
            """
        )
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        conn.execute(
            "INSERT INTO login_attempts VALUES(?,?,?,?,?)",
            ("owner", "127.0.0.1", 5, None, future.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")),
        )
        self.assertGreater(lock_remaining_seconds(conn, "owner", "127.0.0.1"), 0)

        with patch.dict("os.environ", {"STAFF_PAYROLL_LOGIN_FAILURE_LIMIT": "3"}):
            record_login_failure(conn, "payroll", "127.0.0.2")
            record_login_failure(conn, "payroll", "127.0.0.2")
            record_login_failure(conn, "payroll", "127.0.0.2")
        row = conn.execute(
            "SELECT last_failed_at, locked_until FROM login_attempts WHERE identifier='payroll'"
        ).fetchone()
        self.assertTrue(str(row["last_failed_at"]).endswith("+00:00"))
        self.assertTrue(str(row["locked_until"]).endswith("+00:00"))
        conn.close()

    def test_operational_modules_do_not_schedule_retries_with_local_now(self) -> None:
        outbox = (ROOT / "core" / "integration_outbox.py").read_text()
        login = (ROOT / "core" / "login_security.py").read_text()
        backups = (ROOT / "core" / "backups.py").read_text()
        self.assertNotIn("datetime.now()", outbox)
        self.assertNotIn("datetime.now()", login)
        self.assertNotIn("datetime.now()", backups)
        self.assertIn("utc_storage_iso(utc_now() + timedelta", outbox)
        self.assertIn("parse_timestamp_utc", login)
        self.assertIn('"generated_at": utc_iso()', backups)

    def test_schedule_publication_writes_use_aware_application_clock(self) -> None:
        publication = (ROOT / "api" / "schedule_publication.py").read_text()
        acknowledgement = (ROOT / "api" / "staff_schedule_ack.py").read_text()
        self.assertIn("published_at = now_iso()", publication)
        self.assertIn("acknowledged_at = now_iso()", acknowledgement)
        self.assertNotIn("VALUES (?, 'Published', ?, CURRENT_TIMESTAMP", publication)
        self.assertNotIn("acknowledged_at=CURRENT_TIMESTAMP", acknowledgement)

    def test_staff_portal_uses_manila_business_date_and_aware_writes(self) -> None:
        portal = (ROOT / "api" / "staff_published_portal.py").read_text()
        self.assertIn("today = business_today()", portal)
        self.assertNotIn("date.today()", portal)
        self.assertNotIn("date('now','localtime')", portal)
        self.assertNotIn("datetime.now()", portal)
        self.assertIn("now_iso()", portal)

    def test_staff_self_service_uses_manila_business_date_and_shared_clock(self) -> None:
        self_service = (ROOT / "api" / "staff_self_service.py").read_text()
        self.assertNotIn("def now_iso()", self_service)
        self.assertNotIn("date.today()", self_service)
        self.assertNotIn("datetime.now()", self_service)
        self.assertIn("business_today()", self_service)
        self.assertIn("datetime.fromisoformat", self_service)
        self.assertIn("now_iso()", self_service)

    def test_canonical_api_entrypoint_binds_legacy_clock_to_utc(self) -> None:
        source = (ROOT / "api" / "server.py").read_text()
        self.assertIn("core_main_module.now_iso = utc_storage_iso", source)


if __name__ == "__main__":
    unittest.main()
