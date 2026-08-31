from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from api.schedule_change_log import log_schedule_change
from core.db import fetchall, fetchone, now_iso


RECONCILIATION_NOTE = "shift_match=deterministic_reconciliation"
STALE_LINK_NOTE = "shift_match=stale_link_detached"
CONTINUOUS_SEGMENT_NOTE = "shift_match=continuous_split_segmented"


def _append_note(value: Any, note: str) -> str:
    text = str(value or "").strip()
    if note in text:
        return text
    return f"{text} | {note}".strip(" |")


def _clock_datetime(day: str, clock: str, *, next_day_if_needed_from: datetime | None = None) -> datetime:
    value = datetime.fromisoformat(f"{day}T{clock}")
    if next_day_if_needed_from is not None and value <= next_day_if_needed_from:
        value += timedelta(days=1)
    return value


def _shift_interval(work_date: str, shift: dict[str, Any]) -> tuple[datetime, datetime]:
    start = _clock_datetime(work_date, str(shift["start_time"]))
    end = _clock_datetime(work_date, str(shift["end_time"]), next_day_if_needed_from=start)
    return start, end


def _existing_actual_interval(row: dict[str, Any]) -> tuple[datetime, datetime] | None:
    actual_in = str(row.get("actual_in") or "").strip()
    actual_out = str(row.get("actual_out") or "").strip()
    work_date = str(row.get("work_date") or "").strip()
    if not actual_in or not actual_out or not work_date:
        return None
    start = _clock_datetime(work_date, actual_in)
    end = _clock_datetime(work_date, actual_out)
    if end <= start:
        end += timedelta(days=1)
    return start, end


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


def _segment_existing_continuous_log(
    conn,
    row: dict[str, Any],
    shifts: list[dict[str, Any]],
    *,
    employee_id: int,
    work_date: str,
    changed_by: str,
) -> int:
    """Convert one old continuous actual row into exact rows for touching shifts.

    This is the production backfill counterpart of attendance import v2. It only
    runs when every remaining shift touches the next exactly and the one actual
    interval crosses every internal boundary. No gap is inferred or manufactured.
    """

    if len(shifts) < 2:
        return 0
    actual_interval = _existing_actual_interval(row)
    if actual_interval is None:
        return 0
    actual_start, actual_end = actual_interval

    shift_intervals = [_shift_interval(work_date, shift) for shift in shifts]
    for index in range(len(shift_intervals) - 1):
        if shift_intervals[index][1] != shift_intervals[index + 1][0]:
            return 0

    boundaries = [shift_intervals[index][1] for index in range(len(shift_intervals) - 1)]
    if any(not (actual_start < boundary < actual_end) for boundary in boundaries):
        return 0
    if actual_start >= shift_intervals[0][1] or actual_end <= shift_intervals[-1][0]:
        return 0

    stamp = now_iso()
    original = dict(row)
    source_row_id = int(row["id"])
    linked = 0

    for index, shift in enumerate(shifts):
        shift_id = int(shift["id"])
        segment_start = actual_start if index == 0 else shift_intervals[index][0]
        segment_end = actual_end if index == len(shifts) - 1 else shift_intervals[index][1]
        actual_in = segment_start.strftime("%H:%M")
        actual_out = segment_end.strftime("%H:%M")
        marker = f"{CONTINUOUS_SEGMENT_NOTE}:{index + 1}/{len(shifts)}"

        if index == 0:
            before = dict(row)
            conn.execute(
                """
                UPDATE time_logs
                SET scheduled_shift_id=?, actual_in=?, actual_out=?, notes=?, updated_at=?
                WHERE id=? AND scheduled_shift_id IS NULL
                """,
                (
                    shift_id,
                    actual_in,
                    actual_out,
                    _append_note(row.get("notes"), marker),
                    stamp,
                    source_row_id,
                ),
            )
            after = fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (source_row_id,))
            if not after or int(after.get("scheduled_shift_id") or 0) != shift_id:
                return linked
            log_schedule_change(
                conn,
                change_type="segment_continuous_split_shift_actual",
                entity_type="time_log",
                entity_id=source_row_id,
                employee_id=employee_id,
                work_date=work_date,
                before=before,
                after=after,
                changed_by=changed_by,
            )
            linked += 1
            continue

        clone = dict(original)
        clone.pop("id", None)
        clone["scheduled_shift_id"] = shift_id
        clone["actual_in"] = actual_in
        clone["actual_out"] = actual_out
        clone["notes"] = _append_note(original.get("notes"), marker)
        if "updated_at" in clone:
            clone["updated_at"] = stamp
        columns = list(clone.keys())
        placeholders = ",".join("?" for _ in columns)
        cur = conn.execute(
            f"INSERT INTO time_logs ({','.join(columns)}) VALUES ({placeholders})",
            [clone[column] for column in columns],
        )
        new_id = int(cur.lastrowid)
        after = fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (new_id,))
        log_schedule_change(
            conn,
            change_type="segment_continuous_split_shift_actual",
            entity_type="time_log",
            entity_id=new_id,
            employee_id=employee_id,
            work_date=work_date,
            before=None,
            after=after,
            changed_by=changed_by,
        )
        linked += 1

    return linked


def reconcile_unlinked_split_shift_logs(
    conn,
    *,
    employee_id: int | None = None,
    work_date: str | None = None,
    changed_by: str = "system:split-shift-reconciliation",
) -> dict[str, int]:
    """Repair stale links and deterministically reconcile split-shift actuals.

    Besides one-row-per-shift reconciliation, this also backfills historical
    biometric rows that represent one continuous interval spanning multiple
    touching scheduled shifts. Ambiguous, partial, or gapped cases remain alone.
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
    continuous_segments_created = 0

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

        if len(unlinked_rows) == 1 and len(remaining_shifts) > 1:
            segmented = _segment_existing_continuous_log(
                conn,
                unlinked_rows[0],
                remaining_shifts,
                employee_id=group_employee_id,
                work_date=group_work_date,
                changed_by=changed_by,
            )
            if segmented == len(remaining_shifts):
                linked += segmented
                continuous_segments_created += segmented
                groups_linked += 1
                continue

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
        "continuous_segments_created": continuous_segments_created,
    }
