from __future__ import annotations

import inspect
import unittest

from api import integrations, server


class IntegrationReadPurityTests(unittest.TestCase):
    def test_integration_get_handlers_do_not_initialize_schema(self) -> None:
        for handler in (
            integrations.integration_status,
            integrations.integration_readiness,
            integrations.list_events,
            integrations.event_detail,
        ):
            with self.subTest(handler=handler.__name__):
                source = inspect.getsource(handler)
                self.assertNotIn("ensure_integration_schema", source)
                self.assertNotIn("conn.commit()", source)

    def test_integration_write_handlers_keep_defensive_schema_initialization(self) -> None:
        for handler in (
            integrations.retry_event,
            integrations.process_integrations_now,
        ):
            with self.subTest(handler=handler.__name__):
                source = inspect.getsource(handler)
                self.assertIn("ensure_integration_schema(conn)", source)

    def test_runtime_startup_owns_integration_schema(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_integration_schema(conn)", source)


if __name__ == "__main__":
    unittest.main()
