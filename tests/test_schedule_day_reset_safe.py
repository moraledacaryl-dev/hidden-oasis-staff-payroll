from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from api.schedule_day_reset_safe import _split_or_shrink_leave
from core.db import get_conn, init_db, now_iso


class SafeDayResetTests(unittest.TestCase):
    def _conn(self, temp_dir: str) -> sqlite3.Connection:
        db_path = Path(temp_dir) / "reset.sqlite"
        conn = get_conn(db_path)
        init_db(conn)
        conn.execute("INSERT INTO employees(employee_code, full_name, status, created_at, updated_at) VALUES('R-1','Reset User','Active',?,?)", (now_iso(), now_iso()))
        conn.execute("INSERT OR IGNORE INTO leave_types(name, paid, active) VALUES('Vacation Leave', 1, 1)")
        conn.commit()
        return conn

    def _leave_type_id(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT id FROM leave_types WHERE name='Vacation Leave'").fetchone()
        return int(row[0])

    def _leave(self, conn: sqlite3.Connection, start: str, end: str, days: float) -> dict:
        conn.execute(
            "INSERT INTO leave_requests(employee_id, leave_type_id, start_date, end_date, days, paid, status, reason, created_at) VALUES(1, ?, ?, ?, ?, 1, 'Approved', 'Trip', ?)",
            (self._leave_type_id(conn), start, end, days, now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM leave_requests ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row)

    def test_single_day_leave_is_cancelled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            conn = self._conn(temp_dir)
            try:
                row = self._leave(conn, "2026-07-01", "2026-07-01", 1)
                _split_or_shrink_leave(conn, row, date(2026, 7, 1), "Owner", now_iso())
                status = conn.execute("SELECT status FROM leave_requests WHERE id=?", (row["id"],)).fetchone()[0]
                self.assertEqual(status, "Cancelled")
            finally:
                conn.close()

    def test_start_and_end_are_shrunk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            conn = self._conn(temp_dir)
            try:
                row = self._leave(conn, "2026-07-01", "2026-07-03", 3)
                _split_or_shrink_leave(conn, row, date(2026, 7, 1), "Owner", now_iso())
                updated = dict(conn.execute("SELECT * FROM leave_requests WHERE id=?", (row["id"],)).fetchone())
                self.assertEqual(updated["start_date"], "2026-07-02")
                self.assertEqual(float(updated["days"]), 2.0)

                row = self._leave(conn, "2026-08-01", "2026-08-03", 3)
                _split_or_shrink_leave(conn, row, date(2026, 8, 3), "Owner", now_iso())
                updated = dict(conn.execute("SELECT * FROM leave_requests WHERE id=?", (row["id"],)).fetchone())
                self.assertEqual(updated["end_date"], "2026-08-02")
                self.assertEqual(float(updated["days"]), 2.0)
            finally:
                conn.close()

    def test_middle_day_is_split(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            conn = self._conn(temp_dir)
            try:
                row = self._leave(conn, "2026-07-01", "2026-07-05", 5)
                _split_or_shrink_leave(conn, row, date(2026, 7, 3), "Owner", now_iso())
                rows = [dict(item) for item in conn.execute("SELECT start_date, end_date, days, status FROM leave_requests ORDER BY id").fetchall()]
                self.assertEqual(rows[0]["start_date"], "2026-07-01")
                self.assertEqual(rows[0]["end_date"], "2026-07-02")
                self.assertEqual(float(rows[0]["days"]), 2.0)
                self.assertEqual(rows[1]["start_date"], "2026-07-04")
                self.assertEqual(rows[1]["end_date"], "2026-07-05")
                self.assertEqual(float(rows[1]["days"]), 2.0)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
