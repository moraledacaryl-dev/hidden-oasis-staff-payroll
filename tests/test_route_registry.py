from __future__ import annotations

import unittest
from collections import defaultdict

import api.server as server


class ApiRouteRegistryTests(unittest.TestCase):
    def test_no_duplicate_http_method_routes(self) -> None:
        seen: dict[tuple[str, str], list[str]] = defaultdict(list)
        for route in server.app.router.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            endpoint = getattr(route, "endpoint", None)
            if not path or not methods:
                continue
            endpoint_name = getattr(endpoint, "__name__", repr(endpoint))
            for method in methods:
                if method in {"HEAD", "OPTIONS"}:
                    continue
                seen[(str(path), str(method).upper())].append(endpoint_name)
        duplicates = {
            f"{method} {path}": endpoints
            for (path, method), endpoints in sorted(seen.items())
            if len(endpoints) > 1
        }
        self.assertEqual(duplicates, {})

    def test_corrected_override_endpoints_are_active_once(self) -> None:
        endpoints = {
            (str(getattr(route, "path", "")), method): getattr(getattr(route, "endpoint", None), "__name__", "")
            for route in server.app.router.routes
            for method in getattr(route, "methods", set())
            if method not in {"HEAD", "OPTIONS"}
        }
        self.assertEqual(endpoints[("/api/v1/schedules/shifts", "POST")], "create_validated_shift")
        self.assertEqual(endpoints[("/api/v1/schedules/day/scheduled", "POST")], "save_validated_day_schedule")
        self.assertEqual(endpoints[("/api/v1/schedules/day/actual", "POST")], "save_validated_day_actual")
        self.assertEqual(endpoints[("/api/v1/schedules/day/leave", "POST")], "save_day_leave")
        self.assertEqual(endpoints[("/api/v1/me/shift-change-requests/{request_id}/attachment", "POST")], "upload_shift_request_attachment")


if __name__ == "__main__":
    unittest.main()
