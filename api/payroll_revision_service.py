from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from api.payroll_adjustments import ensure_schema as ensure_adjustment_schema
from api.payroll_revision_controls import ensure_revision_schema


class ControlledRevisionPayload(BaseModel):
    run_label: str | None = None
    revision_reason: str
    treatment: Literal["replace_unpaid", "adjust_paid"]


def ensure_workflow_schema(conn) -> None:
    ensure_revision_schema(conn)
    ensure_adjustment_schema(conn)
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(payroll_runs)").fetchall()}
    if "revision_treatment" not in columns:
        conn.execute("ALTER TABLE payroll_runs ADD COLUMN revision_treatment TEXT")
    if "superseded_by_run_id" not in columns:
        conn.execute("ALTER TABLE payroll_runs ADD COLUMN superseded_by_run_id INTEGER")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_revision_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_run_id INTEGER NOT NULL,
            original_run_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            original_net_pay REAL NOT NULL DEFAULT 0,
            revised_net_pay REAL NOT NULL DEFAULT 0,
            adjustment_amount REAL NOT NULL DEFAULT 0,
            adjustment_direction TEXT NOT NULL,
            settlement_status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL,
            UNIQUE(revision_run_id, employee_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_revision_adjustments_run ON payroll_revision_adjustments(revision_run_id)"
    )
    conn.commit()


def is_paid_run(run: dict[str, Any]) -> bool:
    status = str(run.get("status") or "").strip().lower()
    return bool(run.get("paid_at")) or status in {"paid", "released"}
