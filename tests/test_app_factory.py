from __future__ import annotations

import unittest

from api.server import app, create_app


class ApplicationFactoryTests(unittest.TestCase):
    def test_factory_returns_distinct_application_instances(self) -> None:
        first = create_app()
        second = create_app()

        self.assertIsNot(first, second)
        self.assertIsNot(first, app)
        self.assertIsNot(second, app)

    def test_factory_instances_have_equivalent_openapi_contracts(self) -> None:
        first = create_app()
        second = create_app()

        self.assertEqual(first.openapi()["paths"], second.openapi()["paths"])
        self.assertIn("/health", first.openapi()["paths"])
        self.assertIn("/api/v1/schedules/day/scheduled", first.openapi()["paths"])

    def test_factory_does_not_accumulate_routes_between_calls(self) -> None:
        first = create_app()
        first_count = len(first.openapi()["paths"])

        second = create_app()
        second_count = len(second.openapi()["paths"])

        self.assertEqual(first_count, second_count)


if __name__ == "__main__":
    unittest.main()
