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
        seen: dict[tuple[str, str], list[str]] = defaultdict(list)
        for route in server.app.router.routes:
            path = str(getattr(route, "path", ""))
            endpoint_name = getattr(getattr(route, "endpoint", None), "__name__", "")
            for method in getattr(route, "methods", set()):
                if method not in {"HEAD", "OPTIONS"}:
                    seen[(path, method)].append(endpoint_name)

        def active_endpoint(path_suffix: str, method: str = "POST") -> str:
            matches = [
                endpoint
                for (path, route_method), endpoints in seen.items()
                for endpoint in endpoints
                if route_method == method and path.rstrip("/").endswith(path_suffix)
            ]
            self.assertEqual(matches.count(matches[0]) if matches else 0, len(matches), matches)
            self.assertEqual(len(matches), 1, {path_suffix: matches})
            return matches[0]

        self.assertEqual(active_endpoint("/schedules/shifts"), "create_validated_shift")
        self.assertEqual(active_endpoint("/schedules/day/scheduled"), "save_validated_day_schedule")
        self.assertEqual(active_endpoint("/schedules/day/actual"), "save_validated_day_actual")
        self.assertEqual(active_endpoint("/schedules/day/leave"), "save_day_leave")
        self.assertEqual(active_endpoint("/me/shift-change-requests/{request_id}/attachment"), "upload_shift_request_attachment")


if __name__ == "__main__":
    unittest.main()
