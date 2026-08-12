from __future__ import annotations

import unittest

from api.schedules import ensure_schema
from core.db import get_conn, init_db


class FreshScheduleSchemaTests(unittest.TestCase):
    def test_fresh_schema_contains_preflight_review_columns(self) -> None:
        conn = get_conn(":memory:")
        try:
            init_db(conn)
            ensure_schema(conn)

            columns = {
                str(row[1])
                for row in conn.execute(
                    "PRAGMA table_info(scheduled_shifts)"
                ).fetchall()
            }

            required = {
                "review_status",
                "review_reason",
                "reviewed_by",
                "reviewed_at",
                "approved_exception",
            }

            self.assertTrue(
                required.issubset(columns),
                f"Missing scheduled_shifts columns: "
                f"{sorted(required - columns)}",
            )

            # Exercise the same column assumptions used by production preflight.
            count = conn.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT
                        employee_id,
                        shift_date,
                        start_time,
                        end_time,
                        position,
                        department,
                        break_minutes,
                        status,
                        COALESCE(notes, ''),
                        COALESCE(legacy_schedule_id, -1),
                        source,
                        COALESCE(review_status, ''),
                        COALESCE(review_reason, ''),
                        COALESCE(reviewed_by, ''),
                        COALESCE(reviewed_at, ''),
                        approved_exception,
                        COUNT(*) AS c
                    FROM scheduled_shifts
                    GROUP BY
                        employee_id,
                        shift_date,
                        start_time,
                        end_time,
                        position,
                        department,
                        break_minutes,
                        status,
                        COALESCE(notes, ''),
                        COALESCE(legacy_schedule_id, -1),
                        source,
                        COALESCE(review_status, ''),
                        COALESCE(review_reason, ''),
                        COALESCE(reviewed_by, ''),
                        COALESCE(reviewed_at, ''),
                        approved_exception
                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]

            self.assertEqual(count, 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
