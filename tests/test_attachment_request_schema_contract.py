from __future__ import annotations

import inspect
import unittest

import api.server as server
import api.staff_attachment_security as attachment_security


class AttachmentRequestSchemaContractTests(unittest.TestCase):
    def test_attachment_lookup_does_not_run_schema_upgrade(self) -> None:
        source = inspect.getsource(attachment_security._request_for_attachment)
        self.assertNotIn("ensure_attachment_schema", source)
        self.assertNotIn("ensure_schema", source)
        self.assertNotIn("commit(", source)
        self.assertNotIn("ALTER TABLE", source)
        self.assertNotIn("CREATE TABLE", source)

    def test_startup_remains_attachment_schema_owner(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_attachment_schema(conn)", source)


if __name__ == "__main__":
    unittest.main()
