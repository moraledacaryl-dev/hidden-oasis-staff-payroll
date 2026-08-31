from __future__ import annotations

from typing import Any

from api.schedule_change_log import log_schedule_change
from core.db import fetchall, fetchone, now_iso


RECONCILIATION_NOTE = "shift_match=deterministic_reconciliation"


def _append_reconciliation_note(value: Any) -> str:
    text = str(value or "").strip()
    if RECONCILIATION_NOTE in text:
        return text
    return f"{text} | {RECONCILIATION_NOTE}".strip(" |")


def reconcile_unlinked_split_shift_logs(
    conn,
    *,
    employee_id: int | None = None,
    work_date: str | None = None,
    changed_by: str = "system:split-shift-reconciliation",
) -> dict[str, int]:
    """Persist exact shift IDs only when an unlinked mapping is deterministic.

    We never infer a split-shift mapping from a partial or ambiguous set. A group
    is eligible only when every remaining unlinked scheduled shift has exactly one
    remaining unlinked timed attendance row and every actual-in time is distinct.
    Rows and shifts are then paired chronologically, matching the import-v2 rule.
    """

    filters = [
        "tl.scheduled_shift_id IS NULL",
        "COALESCE(tl.attendance_status, '') != 'Rejected'",
        "NULLIF(TRIM(COALESCE(tl.actual_in, '')), '') IS NOT NULL",
    ]
    params: list[Any] = []
    if employee_id is not None:
        filters.append("tl.employee_id=?")
        params.append(int(employee_id))
    if work_date is not None:
        filters.append("date(tl.work_date)=date(?)")
        params.append(str(work_date))

    groups = fetchall(
        conn,
        f"""
        SELECT tl.employee_id, date(tl.work_date) AS work_date
        FROM time_logs tl
        WHERE {' AND '.join(filters)}
        GROUP BY tl.employee_id, date(tl.work_date)
        ORDER BY date(tl.work_date), tl.employee_id
        """,
        params,
    )

    linked = 0
    skipped = 0
    groups_linked = 0

    for group in groups:
        group_employee_id = int(group["employee_id"])
        group_work_date = str(group["work_date"])

        shifts = fetchall(
            conn,
            """
            SELECT id, start_time, end_time
            FROM scheduled_shifts
            WHERE employee_id=? AND date(shift_date)=date(?)
            ORDER BY start_time, id
            """,
            (group_employee_id, group_work_date),
        )
        if len(shifts) < 2:
            skipped += 1
            continue

        already_linked = {
            int(row["scheduled_shift_id"])
            for row in fetchall(
                conn,
                """
                SELECT scheduled_shift_id
                FROM time_logs
                WHERE employee_id=?
                  AND date(work_date)=date(?)
                  AND scheduled_shift_id IS NOT NULL
                  AND COALESCE(attendance_status, '') != 'Rejected'
                """,
                (group_employee_id, group_work_date),
            )
            if row.get("scheduled_shift_id")
        }
        remaining_shifts = [
            shift for shift in shifts if int(shift["id"]) not in already_linked
        ]
        unlinked_rows = fetchall(
            conn,
            """
            SELECT *
            FROM time_logs
            WHERE employee_id=?
              AND date(work_date)=date(?)
              AND scheduled_shift_id IS NULL
              AND COALESCE(attendance_status, '') != 'Rejected'
              AND NULLIF(TRIM(COALESCE(actual_in, '')), '') IS NOT NULL
            ORDER BY actual_in, id
            """,
            (group_employee_id, group_work_date),
        )

        actual_in_values = [str(row.get("actual_in") or "").strip() for row in unlinked_rows]
        if (
            not remaining_shifts
            or len(remaining_shifts) != len(unlinked_rows)
            or len(set(actual_in_values)) != len(actual_in_values)
        ):
            skipped += 1
            continue

        stamp = now_iso()
        for row, shift in zip(unlinked_rows, remaining_shifts, strict=True):
            row_id = int(row["id"])
            shift_id = int(shift["id"])
            before = dict(row)
            conn.execute(
                """
                UPDATE time_logs
                SET scheduled_shift_id=?, notes=?, updated_at=?
                WHERE id=? AND scheduled_shift_id IS NULL
                """,
                (
                    shift_id,
                    _append_reconciliation_note(row.get("notes")),
                    stamp,
                    row_id,
                ),
            )
            after = fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (row_id,))
            if not after or int(after.get("scheduled_shift_id") or 0) != shift_id:
                continue
            log_schedule_change(
                conn,
                change_type="link_split_shift_actual",
                entity_type="time_log",
                entity_id=row_id,
                employee_id=group_employee_id,
                work_date=group_work_date,
                before=before,
                after=after,
                changed_by=changed_by,
            )
            linked += 1

        groups_linked += 1

    return {
        "groups_checked": len(groups),
        "groups_linked": groups_linked,
        "logs_linked": linked,
        "groups_skipped": skipped,
    }
