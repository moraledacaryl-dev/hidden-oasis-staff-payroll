from __future__ import annotations

import unittest
from pathlib import Path


class OwnerMfaResetContractTests(unittest.TestCase):
    def test_reset_revokes_every_mfa_credential(self) -> None:
        source = Path(
            "api/users.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '/users/{user_id}/mfa/reset',
            source,
        )
        self.assertIn(
            "mfa_secret=NULL",
            source,
        )
        self.assertIn(
            "mfa_recovery_codes=NULL",
            source,
        )
        self.assertIn(
            "session_version=COALESCE(session_version,1)+1",
            source,
        )

    def test_owner_password_is_reverified(self) -> None:
        source = Path(
            "api/users.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "payload.owner_password",
            source,
        )
        self.assertIn(
            "Owner password is incorrect.",
            source,
        )


if __name__ == "__main__":
    unittest.main()
