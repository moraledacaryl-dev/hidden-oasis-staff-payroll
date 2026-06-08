import unittest

from core.auth import DEFAULT_TEMP_PASSWORD, authenticate_user, bootstrap_missing_passwords, set_user_password, verify_password
from core.db import fetchone, get_conn, init_db, now_iso


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_conn(":memory:")
        init_db(self.conn)

    def test_bootstrap_adds_temporary_hashed_passwords(self):
        count = bootstrap_missing_passwords(self.conn)
        self.assertGreaterEqual(count, 1)
        user = fetchone(self.conn, "SELECT * FROM app_users WHERE display_name='Caryl / Owner'")
        self.assertTrue(user["password_hash"].startswith("pbkdf2_sha256$"))
        self.assertEqual(user["must_change_password"], 1)
        self.assertTrue(verify_password(DEFAULT_TEMP_PASSWORD, user["password_hash"]))

    def test_authenticate_user_updates_last_login(self):
        bootstrap_missing_passwords(self.conn)
        user = authenticate_user(self.conn, "Caryl / Owner", DEFAULT_TEMP_PASSWORD)
        self.assertIsNotNone(user)
        refreshed = fetchone(self.conn, "SELECT last_login_at FROM app_users WHERE display_name='Caryl / Owner'")
        self.assertTrue(refreshed["last_login_at"])

    def test_set_user_password_replaces_temp_password(self):
        bootstrap_missing_passwords(self.conn)
        user = fetchone(self.conn, "SELECT id FROM app_users WHERE display_name='Caryl / Owner'")
        set_user_password(self.conn, user["id"], "BetterPass123", must_change=False)
        self.assertIsNone(authenticate_user(self.conn, "Caryl / Owner", DEFAULT_TEMP_PASSWORD))
        logged_in = authenticate_user(self.conn, "Caryl / Owner", "BetterPass123")
        self.assertIsNotNone(logged_in)
        self.assertEqual(logged_in["must_change_password"], 0)

    def test_inactive_user_cannot_login(self):
        self.conn.execute(
            "INSERT INTO app_users(display_name, role, active, created_at) VALUES('Inactive', 'Viewer', 0, ?)",
            (now_iso(),),
        )
        self.conn.commit()
        bootstrap_missing_passwords(self.conn)
        self.assertIsNone(authenticate_user(self.conn, "Inactive", DEFAULT_TEMP_PASSWORD))


if __name__ == "__main__":
    unittest.main()
