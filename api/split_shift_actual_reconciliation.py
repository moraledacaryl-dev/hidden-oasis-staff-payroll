from __future__ import annotations

from typing import Any

from api.schedule_change_log import log_schedule_change
from core.db import fetchall, fetchone, now_iso


RECONCILIATION_NOTE = "shift_match=deterministic_reconciliation"
STALE_LINK_NOTE = "shift_match=stale_link_detached"


def _append_note(value: Any, note: str) -> str:
    text = str(value or "").strip()
    if note in text:
        return text
    return f"{text} | {note}".strip(" |")


def _detach_stale_links(
    conn,
    *,
    employee_id: int | None = None,
    work_date: str | None = None,
    changed_by: str,
) -> int:
    filters = [
        "tl.scheduled_shift_id IS NOT NULL",
        "COALESCE(tl.attendance_status, '') != 'Rejected'",
        "(ss.id IS NULL OR COALESCE(ss.employee_id, -1) != tl.employee_id OR date(ss.shift_date) != date(tl.work_date))",
    ]
    params: list[Any] = []
    if employee_id is not None:
        filters.append("tl.employee_id=?")
        params.append(int(employee_id))
    if work_date is not None:
        filters.append("date(tl.work_date)=date(?)")
        params.append(str(work_date))

    stale_rows = fetchall(
        conn,
        f"""
        SELECT tl.*
        FROM time_logs tl
        LEFT JOIN scheduled_shifts ss ON ss.id = tl.scheduled_shift_id
        WHERE {' AND '.join(filters)}
        ORDER BY tl.work_date, tl.employee_id, tl.id
        """,
        params,
    )

    detached = 0
    stamp = now_iso()
    for row in stale_rows:
        row_id = int(row["id"])
        before = dict(row)
        conn.execute(
            """
            UPDATE time_logs
            SET scheduled_shift_id=NULL, notes=?, updated_at=?
            WHERE id=? AND scheduled_shift_id IS NOT NULL
            """,
            (_append_note(row.get("notes"), STALE_LINK_NOTE), stamp, row_id),
        )
        after = fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (row_id,))
        if not after or after.get("scheduled_shift_id") is not None:
            continue
        log_schedule_change(
            conn,
            change_type="detach_stale_split_shift_actual",
            entity_type="time_log",
            entity_id=row_id,
            employee_id=int(row["employee_id"]),
            work_date=str(row["work_date"]),
            before=before,
            after=after,
            changed_by=changed_by,
        )
        detached += 1
    return detached


def reconcile_unlinked_split_shift_logs(
    conn,
    *,
    employee_id: int | None = None,
    work_date: str | None = None,
    changed_by: str = "system:split-shift-reconciliation",
) -> dict[str, int]:
    """Repair stale links, then persist exact shift IDs only when deterministic.

    A stale link is one whose target shift no longer exists or whose employee/date
    no longer matches the time log. Such links are detached first and audited.
    We then link timed rows only when every remaining unlinked scheduled shift has
    exactly one remaining unlinked timed attendance row and all actual-in times are
    distinct. Ambiguous or partial groups remain untouched.
    """

    stale_links_detached = _detach_stale_links(
        conn,
        employee_id=employee_id,
        work_date=work_date,
        changed_by=changed_by,
    )

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
        # Single-shift days already have a safe display fallback. Do not assign
        # a detached orphan automatically because it may belong to a deleted
        # historical shift rather than the one remaining current shift.
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
        linked_this_group = 0
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
                    _append_note(row.get("notes"), RECONCILIATION_NOTE),
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
            linked_this_group += 1

        if linked_this_group:
            groups_linked += 1

    return {
        "groups_checked": len(groups),
        "groups_linked": groups_linked,
        "logs_linked": linked,
        "groups_skipped": skipped,
        "stale_links_detached": stale_links_detached,
    }
