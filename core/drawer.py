from __future__ import annotations

import sqlite3
from typing import Any

from .db import fetchone, get_setting, now_iso


def create_drawer_cash_advance_movement(
    conn: sqlite3.Connection,
    cash_advance_id: int,
    actor: str = "Admin",
    drawer_name: str | None = None,
) -> int | None:
    """Create one drawer cash-out movement for a released cash advance.

    This links drawer reconciliation to the official cash advance record, preventing
    double-entry of the same staff advance as both a payroll item and a drawer expense.
    """
    ca = fetchone(conn, "SELECT * FROM cash_advances WHERE id=?", (cash_advance_id,))
    if not ca:
        return None
    if str(ca.get("release_method") or "").lower() != "cash drawer":
        return None
    if str(ca.get("status") or "") not in ("Released", "Partially Paid"):
        return None
    if ca.get("drawer_movement_id"):
        return int(ca["drawer_movement_id"])

    drawer = drawer_name or get_setting(conn, "main_drawer_name", "Main Drawer") or "Main Drawer"
    cur = conn.execute(
        """
        INSERT INTO cash_drawer_movements(
            movement_date, drawer_name, movement_type, source_type, source_id,
            amount, method, reference, description, created_by, status, created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            (ca.get("released_at") or ca.get("request_date") or now_iso())[:10],
            drawer,
            "Cash Out",
            "Cash Advance",
            cash_advance_id,
            float(ca.get("amount") or 0),
            "Cash",
            ca.get("release_reference") or f"CA-{cash_advance_id}",
            f"Staff cash advance release for employee_id={ca.get('employee_id')}",
            actor,
            "For Reconciliation",
            now_iso(),
        ),
    )
    movement_id = int(cur.lastrowid)
    conn.execute("UPDATE cash_advances SET drawer_movement_id=? WHERE id=?", (movement_id, cash_advance_id))
    conn.execute(
        "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
        (actor, "Created linked drawer cash-out for cash advance", "cash_advances", cash_advance_id, f"drawer_movement_id={movement_id}", now_iso()),
    )
    conn.commit()
    return movement_id


def create_missing_cash_advance_drawer_movements(conn: sqlite3.Connection, actor: str = "Admin") -> int:
    rows = conn.execute(
        """
        SELECT id FROM cash_advances
        WHERE release_method='Cash Drawer'
          AND status IN ('Released','Partially Paid')
          AND (drawer_movement_id IS NULL OR drawer_movement_id='')
        """
    ).fetchall()
    count = 0
    for row in rows:
        if create_drawer_cash_advance_movement(conn, int(row[0]), actor=actor):
            count += 1
    return count
