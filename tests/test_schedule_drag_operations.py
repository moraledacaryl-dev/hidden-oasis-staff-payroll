from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.schedules import (
    DuplicateShiftPayload,
    MoveShiftPayload,
    duplicate_shift,
    move_shift,
)
from core.db import fetchall, fetchone, get_conn, init_db, now_iso


class ScheduleDragOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "schedule-drag.sqlite"
        conn = get_conn(self.db_path)
        try:
            init_db(conn)
            timestamp = now_iso()
            self.source_employee_id = int(
                conn.execute(
                    """
                    INSERT INTO employees(employee_code, full_name, status, created_at, updated_at)
                    VALUES('DRAG-1', 'Source Employee', 'Active', ?, ?)
                    """,
                    (timestamp, timestamp),
                ).lastrowid
            )
            self.target_employee_id = int(
                conn.execute(
                    """
                    INSERT INTO employees(employee_code, full_name, status, created_at, updated_at)
                    VALUES('DRAG-2', 'Target Employee', 'Active', ?, ?)
                    """,
                    (timestamp, timestamp),
                ).lastrowid
            )
            self.shift_id = int(
                conn.execute(
                    """
                    INSERT INTO scheduled_shifts(
                        employee_id, shift_date, start_time, end_time, position,
                        department, break_minutes, notes, source
                    ) VALUES(?, '2026-07-06', '08:00', '17:00', 'Receptionist',
                             'Operations', 60, 'Front desk', 'planned')
                    """,
                    (self.source_employee_id,),
                ).lastrowid
            )
            conn.commit()
        finally:
            conn.close()
        self.actor = {
            "id": 2,
            "display_name": "General Manager",
            "role_key": "supervisor",
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def call_move(self, payload: MoveShiftPayload) -> dict:
        with (
            patch("api.schedules.DB_PATH", self.db_path),
            patch("api.schedules.require_schedule_editor", return_value=self.actor),
        ):
            return move_shift(self.shift_id, payload, authorization=None, x_api_key=None)

    def call_copy(self, payload: DuplicateShiftPayload) -> dict:
        with (
            patch("api.schedules.DB_PATH", self.db_path),
            patch("api.schedules.require_schedule_editor", return_value=self.actor),
        ):
            return duplicate_shift(self.shift_id, payload, authorization=None, x_api_key=None)

    def test_move_uses_destination_employee_and_date(self) -> None:
        result = self.call_move(
            MoveShiftPayload(
                shift_date=date(2026, 7, 7),
                employee_id=self.target_employee_id,
            )
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["shift"]["employee_id"], self.target_employee_id)
        self.assertEqual(result["shift"]["shift_date"], "2026-07-07")

        conn = get_conn(self.db_path)
        try:
            row = fetchone(conn, "SELECT employee_id, shift_date FROM scheduled_shifts WHERE id=?", (self.shift_id,))
            audit = fetchone(conn, "SELECT change_type, employee_id, work_date FROM schedule_change_logs ORDER BY id DESC LIMIT 1")
        finally:
            conn.close()
        self.assertEqual((row["employee_id"], row["shift_date"]), (self.target_employee_id, "2026-07-07"))
        self.assertEqual((audit["change_type"], audit["employee_id"], audit["work_date"]), ("move_schedule", self.target_employee_id, "2026-07-07"))

    def test_copy_preserves_source_and_creates_destination_shift(self) -> None:
        result = self.call_copy(
            DuplicateShiftPayload(
                shift_date=date(2026, 7, 8),
                employee_id=self.target_employee_id,
            )
        )
        self.assertTrue(result["ok"])
        self.assertNotEqual(result["shift"]["id"], self.shift_id)
        self.assertEqual(result["shift"]["employee_id"], self.target_employee_id)
        self.assertEqual(result["shift"]["shift_date"], "2026-07-08")

        conn = get_conn(self.db_path)
        try:
            rows = fetchall(conn, "SELECT employee_id, shift_date FROM scheduled_shifts ORDER BY id")
        finally:
            conn.close()
        self.assertEqual(
            [(row["employee_id"], row["shift_date"]) for row in rows],
            [
                (self.source_employee_id, "2026-07-06"),
                (self.target_employee_id, "2026-07-08"),
            ],
        )

    def test_copy_rejects_an_overlapping_destination_shift(self) -> None:
        conn = get_conn(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO scheduled_shifts(
                    employee_id, shift_date, start_time, end_time, position,
                    department, break_minutes, source
                ) VALUES(?, '2026-07-08', '09:00', '18:00', 'Other',
                         'Operations', 60, 'planned')
                """,
                (self.target_employee_id,),
            )
            conn.commit()
        finally:
            conn.close()

        with self.assertRaises(HTTPException) as raised:
            self.call_copy(
                DuplicateShiftPayload(
                    shift_date=date(2026, 7, 8),
                    employee_id=self.target_employee_id,
                )
            )
        self.assertEqual(raised.exception.status_code, 409)

        conn = get_conn(self.db_path)
        try:
            count = int(fetchone(conn, "SELECT COUNT(*) AS count FROM scheduled_shifts")["count"])
        finally:
            conn.close()
        self.assertEqual(count, 2)

    def test_move_without_employee_field_preserves_assignment(self) -> None:
        result = self.call_move(MoveShiftPayload(shift_date=date(2026, 7, 9)))
        self.assertEqual(result["shift"]["employee_id"], self.source_employee_id)

    def test_move_to_unassigned_clears_employee(self) -> None:
        result = self.call_move(
            MoveShiftPayload(
                shift_date=date(2026, 7, 9),
                employee_id=None,
            )
        )
        self.assertIsNone(result["shift"]["employee_id"])

        conn = get_conn(self.db_path)
        try:
            row = fetchone(
                conn,
                "SELECT employee_id, shift_date FROM scheduled_shifts WHERE id=?",
                (self.shift_id,),
            )
        finally:
            conn.close()
        self.assertIsNone(row["employee_id"])
        self.assertEqual(row["shift_date"], "2026-07-09")


if __name__ == "__main__":
    unittest.main()
