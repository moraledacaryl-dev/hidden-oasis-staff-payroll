from __future__ import annotations

import sqlite3
from typing import Any


def _destination_for(event_type: str) -> str:
    return "accounting" if event_type in {
        "employee.sync",
        "payroll.run.approved",
        "payroll.run.paid",
        "payroll.13th_month.paid",
        "cash_advance.released",
        "cash_advance.repaid",
    } else "operations"


def install_legacy_enqueue_adapter() -> None:
    """Bridge legacy producers/readers onto the durable destination-aware outbox.

    Legacy payroll helpers still expect Ready/Sent rows and a sent_at column.
    The durable worker uses Pending/Retry/Completed. This adapter preserves both
    contracts without allowing duplicate delivery or mutating Completed events.
    """
    from core import integration_accounting, integration_outbox

    original_ensure_schema = integration_outbox.ensure_integration_schema
    original_claim_events = integration_outbox.claim_events

    def compatible_ensure_schema(conn: sqlite3.Connection) -> None:
        original_ensure_schema(conn)
        columns = {
            item[1]
            for item in conn.execute("PRAGMA table_info(integration_outbox)").fetchall()
        }
        if "sent_at" not in columns:
            conn.execute("ALTER TABLE integration_outbox ADD COLUMN sent_at TEXT")
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_integration_outbox_completed_sent_at
            AFTER UPDATE OF status ON integration_outbox
            WHEN NEW.status='Completed' AND NEW.sent_at IS NULL
            BEGIN
                UPDATE integration_outbox
                SET sent_at=COALESCE(NEW.completed_at, NEW.updated_at)
                WHERE id=NEW.id;
            END
            """
        )
        conn.commit()

    def compatible_claim_events(
        conn: sqlite3.Connection,
        *,
        limit: int = 25,
        worker_id: str | None = None,
    ) -> list[dict[str, Any]]:
        compatible_ensure_schema(conn)
        # Rows created by still-supported legacy producers remain claimable by
        # the durable worker. Conversion happens immediately before claiming.
        conn.execute(
            """
            UPDATE integration_outbox
            SET status='Pending', updated_at=COALESCE(updated_at, CURRENT_TIMESTAMP)
            WHERE status='Ready'
            """
        )
        conn.execute(
            """
            UPDATE integration_outbox
            SET status='Retry', updated_at=COALESCE(updated_at, CURRENT_TIMESTAMP)
            WHERE status='Error'
            """
        )
        conn.commit()
        return original_claim_events(conn, limit=limit, worker_id=worker_id)

    integration_outbox.ensure_integration_schema = compatible_ensure_schema
    integration_outbox.claim_events = compatible_claim_events

    def compatible_enqueue_payload(
        conn: sqlite3.Connection,
        event_type: str,
        external_id: str,
        source_type: str,
        source_id: int | None,
        payload: dict[str, Any],
    ) -> int:
        event_id = integration_outbox.enqueue_event(
            conn,
            destination=_destination_for(event_type),
            event_type=event_type,
            external_source=integration_accounting.EXTERNAL_SOURCE,
            external_id=external_id,
            source_type=source_type,
            source_id=source_id,
            payload=payload,
        )
        # Preserve legacy manual-delivery behavior while keeping Completed rows
        # immutable. The durable worker converts Ready to Pending when claiming.
        conn.execute(
            """
            UPDATE integration_outbox
            SET status='Ready', updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND status NOT IN ('Completed','Sent')
            """,
            (event_id,),
        )
        conn.commit()
        return event_id

    integration_accounting.enqueue_payload = compatible_enqueue_payload


def ensure_legacy_integration_writer_compatibility(conn: sqlite3.Connection) -> None:
    """Keep older database writes readable while producers migrate."""
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
            item[1]
            for item in conn.execute(
                "PRAGMA table_info(integration_outbox_durable)"
            ).fetchall()
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
    else:
        columns = {
            item[1]
            for item in conn.execute("PRAGMA table_info(integration_outbox)").fetchall()
        }
        if "sent_at" not in columns:
            conn.execute("ALTER TABLE integration_outbox ADD COLUMN sent_at TEXT")

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
                completed_at = CASE
                    WHEN NEW.status='Sent'
                    THEN COALESCE(NEW.sent_at, NEW.updated_at)
                    ELSE NEW.completed_at
                END,
                sent_at = CASE
                    WHEN NEW.status='Sent'
                    THEN COALESCE(NEW.sent_at, NEW.updated_at)
                    ELSE NEW.sent_at
                END
            WHERE id=NEW.id;
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_integration_outbox_completed_sent_at
        AFTER UPDATE OF status ON integration_outbox
        WHEN NEW.status='Completed' AND NEW.sent_at IS NULL
        BEGIN
            UPDATE integration_outbox
            SET sent_at=COALESCE(NEW.completed_at, NEW.updated_at)
            WHERE id=NEW.id;
        END
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_integration_outbox_delivery "
        "ON integration_outbox(status,next_attempt_at,destination,id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_integration_outbox_source "
        "ON integration_outbox(source_type,source_id,event_type)"
    )
    conn.commit()


install_legacy_enqueue_adapter()
