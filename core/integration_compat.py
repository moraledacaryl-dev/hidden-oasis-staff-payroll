from __future__ import annotations

import sqlite3


def ensure_legacy_integration_writer_compatibility(conn: sqlite3.Connection) -> None:
    """Keep older enqueue helpers working while all producers migrate to the durable outbox API.

    Older code inserts rows without destination and uses Ready/Sent/Error states. The
    compatibility rebuild gives destination a safe default and normalizes new legacy
    inserts through a trigger. This can be removed after every producer uses
    core.integration_outbox.enqueue_event directly.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='integration_outbox'"
    ).fetchone()
    table_sql = str(row[0] or "") if row else ""
    if "destination TEXT NOT NULL DEFAULT 'accounting'" not in table_sql:
        conn.execute("ALTER TABLE integration_outbox RENAME TO integration_outbox_durable")
        conn.execute(
            """
            CREATE TABLE integration_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                destination TEXT NOT NULL DEFAULT 'accounting',
                event_type TEXT NOT NULL,
                external_source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                source_type TEXT,
                source_id INTEGER,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 8,
                next_attempt_at TEXT,
                last_attempt_at TEXT,
                last_error TEXT,
                response_json TEXT,
                locked_at TEXT,
                locked_by TEXT,
                completed_at TEXT,
                dead_letter_at TEXT,
                sent_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(destination, external_source, external_id)
            )
            """
        )
        durable_columns = {
            item[1] for item in conn.execute("PRAGMA table_info(integration_outbox_durable)").fetchall()
        }
        target_columns = [
            "id", "destination", "event_type", "external_source", "external_id",
            "source_type", "source_id", "payload_json", "status", "attempt_count",
            "max_attempts", "next_attempt_at", "last_attempt_at", "last_error",
            "response_json", "locked_at", "locked_by", "completed_at",
            "dead_letter_at", "sent_at", "created_at", "updated_at",
        ]
        select_parts = []
        for column in target_columns:
            if column in durable_columns:
                select_parts.append(column)
            elif column == "sent_at" and "completed_at" in durable_columns:
                select_parts.append("completed_at AS sent_at")
            elif column == "destination":
                select_parts.append("'accounting' AS destination")
            elif column == "status":
                select_parts.append("'Pending' AS status")
            elif column == "attempt_count":
                select_parts.append("0 AS attempt_count")
            elif column == "max_attempts":
                select_parts.append("8 AS max_attempts")
            else:
                select_parts.append(f"NULL AS {column}")
        conn.execute(
            f"INSERT INTO integration_outbox({','.join(target_columns)}) "
            f"SELECT {','.join(select_parts)} FROM integration_outbox_durable"
        )
        conn.execute("DROP TABLE integration_outbox_durable")

    conn.execute("DROP TRIGGER IF EXISTS trg_integration_outbox_legacy_insert")
    conn.execute(
        """
        CREATE TRIGGER trg_integration_outbox_legacy_insert
        AFTER INSERT ON integration_outbox
        WHEN NEW.status IN ('Ready','Sent','Error')
        BEGIN
            UPDATE integration_outbox
            SET destination = CASE
                    WHEN NEW.event_type IN (
                        'employee.sync','payroll.run.approved','payroll.run.paid',
                        'payroll.13th_month.paid','cash_advance.released','cash_advance.repaid'
                    ) THEN 'accounting'
                    ELSE 'operations'
                END,
                status = CASE NEW.status
                    WHEN 'Ready' THEN 'Pending'
                    WHEN 'Sent' THEN 'Completed'
                    WHEN 'Error' THEN 'Retry'
                    ELSE NEW.status
                END,
                completed_at = CASE WHEN NEW.status='Sent' THEN COALESCE(NEW.sent_at, NEW.updated_at) ELSE NEW.completed_at END
            WHERE id=NEW.id;
        END
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_integration_outbox_delivery ON integration_outbox(status,next_attempt_at,destination,id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_integration_outbox_source ON integration_outbox(source_type,source_id,event_type)")
    conn.commit()
