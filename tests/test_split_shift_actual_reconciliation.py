import sqlite3

from api.schedule_change_log import ensure_schedule_change_log_schema
from api.split_shift_actual_reconciliation import reconcile_unlinked_split_shift_logs


def build_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE scheduled_shifts (
            id INTEGER PRIMARY KEY,
            employee_id INTEGER NOT NULL,
            shift_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL
        );
        CREATE TABLE time_logs (
            id INTEGER PRIMARY KEY,
            scheduled_shift_id INTEGER,
            employee_id INTEGER NOT NULL,
            work_date TEXT NOT NULL,
            actual_in TEXT,
            actual_out TEXT,
            attendance_status TEXT NOT NULL DEFAULT 'Approved',
            notes TEXT,
            updated_at TEXT
        );
        """
    )
    ensure_schedule_change_log_schema(conn)
    return conn


def test_reconciles_two_existing_unlinked_logs_to_two_split_shifts():
    conn = build_conn()
    conn.executemany(
        "INSERT INTO scheduled_shifts(id,employee_id,shift_date,start_time,end_time) VALUES(?,?,?,?,?)",
        [
            (11, 7, "2026-08-30", "08:00", "12:00"),
            (12, 7, "2026-08-30", "13:00", "17:00"),
        ],
    )
    conn.executemany(
        "INSERT INTO time_logs(id,employee_id,work_date,actual_in,actual_out,attendance_status,notes) VALUES(?,?,?,?,?,?,?)",
        [
            (101, 7, "2026-08-30", "08:04", "12:02", "Approved", "first"),
            (102, 7, "2026-08-30", "13:03", "17:01", "Approved", "second"),
        ],
    )

    result = reconcile_unlinked_split_shift_logs(conn)
    conn.commit()

    rows = conn.execute(
        "SELECT id,scheduled_shift_id,notes FROM time_logs ORDER BY id"
    ).fetchall()
    assert result["logs_linked"] == 2
    assert [(row["id"], row["scheduled_shift_id"]) for row in rows] == [(101, 11), (102, 12)]
    assert all("shift_match=deterministic_reconciliation" in row["notes"] for row in rows)
    assert conn.execute(
        "SELECT COUNT(*) FROM schedule_change_logs WHERE change_type='link_split_shift_actual'"
    ).fetchone()[0] == 2


def test_does_not_guess_when_split_shift_mapping_is_incomplete():
    conn = build_conn()
    conn.executemany(
        "INSERT INTO scheduled_shifts(id,employee_id,shift_date,start_time,end_time) VALUES(?,?,?,?,?)",
        [
            (21, 8, "2026-08-30", "08:00", "12:00"),
            (22, 8, "2026-08-30", "13:00", "17:00"),
        ],
    )
    conn.execute(
        "INSERT INTO time_logs(id,employee_id,work_date,actual_in,actual_out,attendance_status) VALUES(?,?,?,?,?,?)",
        (201, 8, "2026-08-30", "08:05", "12:00", "Approved"),
    )

    result = reconcile_unlinked_split_shift_logs(conn)

    row = conn.execute("SELECT scheduled_shift_id FROM time_logs WHERE id=201").fetchone()
    assert result["logs_linked"] == 0
    assert row["scheduled_shift_id"] is None


def test_links_only_the_remaining_unmatched_shift_when_other_shift_is_already_linked():
    conn = build_conn()
    conn.executemany(
        "INSERT INTO scheduled_shifts(id,employee_id,shift_date,start_time,end_time) VALUES(?,?,?,?,?)",
        [
            (31, 9, "2026-08-30", "08:00", "12:00"),
            (32, 9, "2026-08-30", "13:00", "17:00"),
        ],
    )
    conn.executemany(
        "INSERT INTO time_logs(id,scheduled_shift_id,employee_id,work_date,actual_in,actual_out,attendance_status) VALUES(?,?,?,?,?,?,?)",
        [
            (301, 31, 9, "2026-08-30", "08:00", "12:00", "Approved"),
            (302, None, 9, "2026-08-30", "13:02", "17:00", "Approved"),
        ],
    )

    result = reconcile_unlinked_split_shift_logs(conn)

    assert result["logs_linked"] == 1
    assert conn.execute(
        "SELECT scheduled_shift_id FROM time_logs WHERE id=302"
    ).fetchone()[0] == 32
