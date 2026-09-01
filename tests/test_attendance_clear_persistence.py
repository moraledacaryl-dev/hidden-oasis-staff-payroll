from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from api.schedule_rest_days import RestDayPayload, ensure_schema as ensure_rest_schema, save_rest_day
from api.schedules import ensure_schema as ensure_schedule_schema
from core.db import get_conn, init_db, now_iso
from core.payroll_engine import compute_payroll


def _db(temp_dir: str) -> Path:
    path = Path(temp_dir) / "attendance-clear.sqlite"
    conn = get_conn(path)
    init_db(conn)
    ensure_schedule_schema(conn)
    ensure_rest_schema(conn)
    stamp = now_iso()
    conn.execute("DELETE FROM employees")
    conn.execute(
        """
        INSERT INTO employees(
            id, employee_code, full_name, department, position, employment_type,
            status, hourly_rate, daily_rate, declared_monthly_base,
            standard_shift_hours, unpaid_break_minutes, security_no_break,
            benefits_sss, benefits_philhealth, benefits_pagibig, benefits_tax,
            created_at, updated_at
        ) VALUES(13,'EMP-010','Monico Jamora','Operations','Staff','Hourly',
                 'Active',62.50,0,0,8,0,0,0,0,0,0,?,?)
        """,
        (stamp, stamp),
    )
    conn.commit()
    conn.close()
    return path


def _insert_stale_actual(conn, work_date: str = "2026-08-19") -> int:
    cur = conn.execute(
        """
        INSERT INTO time_logs(
            employee_id, work_date, actual_in, actual_out, source,
            verification_type, is_absent, approved_ot_hours, ot_status,
            attendance_status, scheduled_shift_id, created_at, updated_at
        ) VALUES(13, ?, '21:00', '07:01', 'Biometric Import', 'Biometric',
                 0, 0, 'None', 'Approved', NULL, ?, ?)
        """,
        (work_date, now_iso(), now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def _mark_rest_directly(conn, work_date: str = "2026-08-19") -> None:
    stamp = now_iso()
    conn.execute(
        """
        INSERT INTO schedule_day_markers(
            employee_id,work_date,marker_type,notes,active,
            created_by,created_at,updated_by,updated_at
        ) VALUES(13,?,'Rest Day','Cleared in schedule',1,'Owner',?,'Owner',?)
        """,
        (work_date, stamp, stamp),
    )
    conn.commit()


def test_existing_rest_day_marker_suppresses_surviving_stale_actual_from_payroll() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = _db(temp_dir)
        conn = get_conn(path)
        try:
            _insert_stale_actual(conn)
            _mark_rest_directly(conn)
            result = next(item for item in compute_payroll(conn, "2026-08-19", "2026-08-19") if item.employee_id == 13)
            assert result.regular_hours == 0
            assert result.approved_ot_hours == 0
            assert result.regular_pay == 0
            assert result.ot_pay == 0
        finally:
            conn.close()


def test_marking_rest_day_purges_old_unlinked_actual_and_audits_it() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = _db(temp_dir)
        conn = get_conn(path)
        try:
            stale_id = _insert_stale_actual(conn)
        finally:
            conn.close()

        with (
            patch("api.schedule_rest_days.DB_PATH", path),
            patch("api.schedule_rest_days.require_editor", return_value={"display_name": "Owner", "role_key": "owner"}),
        ):
            response = save_rest_day(RestDayPayload(employee_id=13, work_date=date(2026, 8, 19), active=True), None, None)
        assert response["ok"] is True

        conn = get_conn(path)
        try:
            assert conn.execute("SELECT COUNT(*) FROM time_logs WHERE id=?", (stale_id,)).fetchone()[0] == 0
            audit = conn.execute(
                """
                SELECT change_type, before_json, after_json
                FROM schedule_change_logs
                WHERE entity_type='time_log' AND entity_id=?
                ORDER BY id DESC LIMIT 1
                """,
                (stale_id,),
            ).fetchone()
            assert audit is not None
            assert audit[0] == "clear_actual_for_rest_day"
            assert "21:00" in str(audit[1])
            assert audit[2] is None
            result = next(item for item in compute_payroll(conn, "2026-08-19", "2026-08-19") if item.employee_id == 13)
            assert result.regular_hours == 0
            assert result.approved_ot_hours == 0
        finally:
            conn.close()


def test_rest_day_clear_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = _db(temp_dir)
        conn = get_conn(path)
        try:
            _insert_stale_actual(conn)
        finally:
            conn.close()

        with (
            patch("api.schedule_rest_days.DB_PATH", path),
            patch("api.schedule_rest_days.require_editor", return_value={"display_name": "Owner", "role_key": "owner"}),
        ):
            payload = RestDayPayload(employee_id=13, work_date=date(2026, 8, 19), active=True)
            assert save_rest_day(payload, None, None)["ok"] is True
            assert save_rest_day(payload, None, None)["ok"] is True

        conn = get_conn(path)
        try:
            assert conn.execute("SELECT COUNT(*) FROM time_logs WHERE employee_id=13 AND work_date='2026-08-19'").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM schedule_day_markers WHERE employee_id=13 AND work_date='2026-08-19' AND marker_type='Rest Day' AND active=1").fetchone()[0] == 1
        finally:
            conn.close()


def test_actual_save_contract_persists_explicit_nulls() -> None:
    source = Path("api/schedules.py").read_text()
    block = source.split('def save_day_actual', 1)[1].split('@router.post("/schedules/day/leave")', 1)[0]
    assert "actual_in=?" in block
    assert "actual_out=?" in block
    assert "payload.actual_in" in block
    assert "payload.actual_out" in block


def test_weekly_schedule_read_remains_side_effect_free() -> None:
    source = Path("api/schedule_actuals.py").read_text()
    assert "reconcile_unlinked_split_shift_logs" not in source
