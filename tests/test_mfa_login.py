from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException

from api.main import LoginRequest, build_app
from core.auth import TOTP_STEP_SECONDS, _totp_code, hash_password
from core.db import get_conn, init_db, now_iso


class MfaLoginEnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "staff.sqlite"

        self.secret = "JBSWY3DPEHPK3PXP"
        self.password = "CorrectPassword123!"

        self.env = patch.dict(
            os.environ,
            {
                "STAFF_PAYROLL_DB_PATH": str(self.db_path),
                "STAFF_PAYROLL_SESSION_SECRET":
                    "mfa-login-test-secret-that-is-long",
                "STAFF_PAYROLL_API_KEY": "",
            },
            clear=False,
        )
        self.env.start()

        conn = get_conn(self.db_path)
        try:
            init_db(conn)
            conn.execute(
                """
                INSERT INTO app_users(
                    display_name,
                    role,
                    password_hash,
                    active,
                    must_change_password,
                    session_version,
                    mfa_enabled,
                    mfa_secret,
                    mfa_confirmed_at,
                    created_at
                )
                VALUES (?, 'Payroll', ?, 1, 0, 1, 1, ?, ?, ?)
                """,
                (
                    "MFA Payroll",
                    hash_password(self.password),
                    self.secret,
                    now_iso(),
                    now_iso(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        app = build_app()
        self.login_endpoint = next(
            route.endpoint
            for route in app.routes
            if getattr(route, "path", "") == "/api/v1/auth/login"
            and "POST" in getattr(route, "methods", set())
        )

        request = Mock()
        request.client = Mock()
        request.client.host = "127.0.0.1"
        self.request = request

    def tearDown(self) -> None:
        self.env.stop()
        self.tempdir.cleanup()

    def login(self, otp: str | None = None):
        return self.login_endpoint(
            LoginRequest(
                display_name="MFA Payroll",
                password=self.password,
                otp=otp,
            ),
            self.request,
        )

    def current_code(self) -> str:
        counter = int(time.time()) // TOTP_STEP_SECONDS
        return _totp_code(self.secret, counter)

    def test_mfa_enabled_login_without_otp_does_not_issue_session(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            self.login()

        self.assertEqual(raised.exception.status_code, 428)
        self.assertEqual(
            raised.exception.detail,
            "Authenticator code required.",
        )

    def test_mfa_enabled_login_rejects_invalid_otp(self) -> None:
        current = self.current_code()
        bad = "000000" if current != "000000" else "999999"

        with self.assertRaises(HTTPException) as raised:
            self.login(bad)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(
            raised.exception.detail,
            "Authenticator code is invalid.",
        )

    def test_mfa_enabled_login_accepts_valid_otp_and_reports_mfa_state(self) -> None:
        result = self.login(self.current_code())

        self.assertTrue(result["access_token"])
        self.assertEqual(result["user"]["mfa_enabled"], 1)

        conn = get_conn(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT last_login_at
                FROM app_users
                WHERE display_name='MFA Payroll'
                """
            ).fetchone()

            self.assertTrue(row[0])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
