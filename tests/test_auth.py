import unittest

from core.auth import (
    authenticate_user,
    bootstrap_missing_passwords,
    generate_totp_secret,
    provision_owner,
    set_user_password,
    verify_password,
    verify_totp,
)
from core.db import fetchone, get_conn, init_db, now_iso


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_conn(":memory:")
        init_db(self.conn)
        self.conn.execute(
            """
            INSERT INTO app_users(display_name, role, active, created_at)
            VALUES('Caryl / Owner', 'Owner', 1, ?), ('General Manager', 'General Manager', 1, ?)
            """,
            (now_iso(), now_iso()),
        )
        self.conn.commit()

    def test_bootstrap_adds_temporary_hashed_passwords(self):
        generated = bootstrap_missing_passwords(self.conn)
        self.assertGreaterEqual(len(generated), 1)
        user = fetchone(self.conn, "SELECT * FROM app_users WHERE display_name='Caryl / Owner'")
        self.assertTrue(user["password_hash"].startswith("pbkdf2_sha256$"))
        self.assertEqual(user["must_change_password"], 1)
        self.assertTrue(verify_password(generated[int(user["id"])], user["password_hash"]))

    def test_authenticate_user_updates_last_login(self):
        generated = bootstrap_missing_passwords(self.conn)
        owner = fetchone(self.conn, "SELECT id FROM app_users WHERE display_name='Caryl / Owner'")
        user = authenticate_user(self.conn, "Caryl / Owner", generated[int(owner["id"])])
        self.assertIsNotNone(user)
        refreshed = fetchone(self.conn, "SELECT last_login_at FROM app_users WHERE display_name='Caryl / Owner'")
        self.assertTrue(refreshed["last_login_at"])

    def test_credential_check_can_wait_for_mfa_before_recording_login(self):
        generated = bootstrap_missing_passwords(self.conn)
        owner = fetchone(self.conn, "SELECT id FROM app_users WHERE display_name='Caryl / Owner'")
        user = authenticate_user(
            self.conn,
            "Caryl / Owner",
            generated[int(owner["id"])],
            record_login=False,
        )
        self.assertIsNotNone(user)
        refreshed = fetchone(
            self.conn,
            "SELECT last_login_at FROM app_users WHERE display_name='Caryl / Owner'",
        )
        self.assertIsNone(refreshed["last_login_at"])

    def test_set_user_password_replaces_temp_password(self):
        generated = bootstrap_missing_passwords(self.conn)
        user = fetchone(self.conn, "SELECT id FROM app_users WHERE display_name='Caryl / Owner'")
        set_user_password(self.conn, user["id"], "BetterPass123", must_change=False)
        self.assertIsNone(authenticate_user(self.conn, "Caryl / Owner", generated[int(user["id"])]))
        logged_in = authenticate_user(self.conn, "Caryl / Owner", "BetterPass123")
        self.assertIsNotNone(logged_in)
        self.assertEqual(logged_in["must_change_password"], 0)

    def test_inactive_user_cannot_login(self):
        self.conn.execute(
            "INSERT INTO app_users(display_name, role, active, created_at) VALUES('Inactive', 'Viewer', 0, ?)",
            (now_iso(),),
        )
        self.conn.commit()
        generated = bootstrap_missing_passwords(self.conn)
        self.assertNotIn(-1, generated)
        self.assertIsNone(authenticate_user(self.conn, "Inactive", "anything"))

    def test_provision_owner_creates_and_resets_explicit_owner(self):
        user_id = provision_owner(self.conn, "Deployment Owner", "LongOwnerPass123")
        user = fetchone(self.conn, "SELECT * FROM app_users WHERE id=?", (user_id,))
        self.assertEqual(user["role"], "Owner")
        self.assertEqual(user["must_change_password"], 1)
        self.assertTrue(verify_password("LongOwnerPass123", user["password_hash"]))

        same_id = provision_owner(
            self.conn,
            "Deployment Owner",
            "AnotherOwnerPass456",
            must_change=False,
        )
        self.assertEqual(same_id, user_id)
        refreshed = fetchone(self.conn, "SELECT * FROM app_users WHERE id=?", (user_id,))
        self.assertEqual(refreshed["must_change_password"], 0)
        self.assertTrue(verify_password("AnotherOwnerPass456", refreshed["password_hash"]))

    def test_totp_codes_validate_only_near_current_window(self):
        secret = generate_totp_secret()
        from core.auth import _totp_code

        code = _totp_code(secret, 1_000_000 // 30)
        self.assertTrue(verify_totp(secret, code, at_time=1_000_000))
        self.assertFalse(verify_totp(secret, "000000", at_time=1_000_000))


if __name__ == "__main__":
    unittest.main()
