from __future__ import annotations

import sqlite3
import unittest

from core.integration_outbox import ensure_integration_schema


class IntegrationLegacyStatusTests(unittest.TestCase):
    def test_legacy_ready_status_becomes_pending(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        try:
            ensure_integration_schema(conn)

            conn.execute(
                """
                INSERT INTO integration_outbox(
                    destination,
                    event_type,
                    external_source,
                    external_id,
                    payload_json,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (
                    'accounting',
                    'payroll.run.approved',
                    'test',
                    'legacy-ready',
                    '{}',
                    'Ready',
                    '2026-01-01 00:00:00',
                    '2026-01-01 00:00:00'
                )
                """
            )
            conn.commit()

            ensure_integration_schema(conn)

            row = conn.execute(
                """
                SELECT status
                FROM integration_outbox
                WHERE external_id='legacy-ready'
                """
            ).fetchone()

            self.assertEqual(
                row["status"],
                "Pending",
            )
        finally:
            conn.close()

    def test_legacy_sent_and_error_are_normalized(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        try:
            ensure_integration_schema(conn)

            for external_id, status in (
                ("legacy-sent", "Sent"),
                ("legacy-error", "Error"),
            ):
                conn.execute(
                    """
                    INSERT INTO integration_outbox(
                        destination,
                        event_type,
                        external_source,
                        external_id,
                        payload_json,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'accounting',
                        'payroll.run.approved',
                        'test',
                        ?,
                        '{}',
                        ?,
                        '2026-01-01 00:00:00',
                        '2026-01-01 00:00:00'
                    )
                    """,
                    (external_id, status),
                )

            conn.commit()
            ensure_integration_schema(conn)

            statuses = dict(
                conn.execute(
                    """
                    SELECT external_id, status
                    FROM integration_outbox
                    """
                ).fetchall()
            )

            self.assertEqual(
                statuses["legacy-sent"],
                "Completed",
            )
            self.assertEqual(
                statuses["legacy-error"],
                "Retry",
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
