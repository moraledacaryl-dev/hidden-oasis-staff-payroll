import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from api import users
from core.auth import hash_password, authenticate_user
from core.db import get_conn, init_db, now_iso


class LoginNameChangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / 'test.db')
        conn = get_conn(self.db)
        init_db(conn)
        conn.execute("INSERT INTO app_users(display_name, role, active, password_hash, must_change_password, created_at) VALUES(?, 'Staff', 1, ?, 1, ?)", ('Jojo Ucat', hash_password('LongTemporaryPassword123'), now_iso()))
        self.user_id = conn.execute("SELECT id FROM app_users WHERE display_name='Jojo Ucat'").fetchone()[0]
        conn.execute("INSERT INTO app_users(display_name, role, active, created_at) VALUES('other.user', 'Staff', 1, ?)", (now_iso(),))
        conn.commit()
        conn.close()
        self.patches = [patch.object(users, 'DB_PATH', self.db), patch.object(users, 'require_owner', return_value={'id': 99, 'display_name': 'Owner'})]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in self.patches: item.stop()
        self.temp.cleanup()

    def test_rename_preserves_password_and_account(self):
        users.set_user_login_name(self.user_id, users.ChangeLoginNameRequest(display_name='jojo.ucat'), None, None)
        conn = get_conn(self.db)
        user = authenticate_user(conn, 'jojo.ucat', 'LongTemporaryPassword123')
        self.assertEqual(user['id'], self.user_id)
        self.assertEqual(user['must_change_password'], 1)
        self.assertIsNone(authenticate_user(conn, 'Jojo Ucat', 'LongTemporaryPassword123'))
        conn.close()

    def test_duplicate_and_blank_names_rejected(self):
        for name, status in [('OTHER.USER', 409), ('   ', 422)]:
            with self.subTest(name=name), self.assertRaises(HTTPException) as error:
                users.set_user_login_name(self.user_id, users.ChangeLoginNameRequest(display_name=name), None, None)
            self.assertEqual(error.exception.status_code, status)

    def test_owner_required(self):
        with patch.object(users, 'require_owner', side_effect=HTTPException(status_code=403)):
            with self.assertRaises(HTTPException) as error:
                users.set_user_login_name(self.user_id, users.ChangeLoginNameRequest(display_name='jojo.ucat'), None, None)
            self.assertEqual(error.exception.status_code, 403)
