from __future__ import annotations

import unittest
from collections import defaultdict
from typing import Any, Iterable

import api.server as server


def walk_routes(routes: Iterable[Any]) -> Iterable[Any]:
    for route in routes:
        nested = getattr(route, "routes", None)
        if nested:
            yield from walk_routes(nested)
        else:
            yield route


class ApiRouteRegistryTests(unittest.TestCase):
    def test_no_duplicate_http_method_routes(self) -> None:
        seen: dict[tuple[str, str], list[str]] = defaultdict(list)
        for route in walk_routes(server.app.router.routes):
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

    def test_corrected_override_endpoints_are_exposed_once_in_openapi(self) -> None:
        paths = server.app.openapi()["paths"]
        expected_operation_prefixes = {
            "/api/v1/schedules/shifts": "create_shift",
            "/api/v1/schedules/day/scheduled": "save_day_schedule",
            "/api/v1/schedules/day/actual": "save_day_actual",
            "/api/v1/schedules/day/leave": "save_day_leave",
        }
        for path, expected_prefix in expected_operation_prefixes.items():
            self.assertIn(path, paths)
            self.assertIn("post", paths[path])
            operation_id = str(paths[path]["post"].get("operationId") or "")
            self.assertTrue(
                operation_id.startswith(expected_prefix),
                {"path": path, "operationId": operation_id, "expected_prefix": expected_prefix},
            )

    def test_staff_upload_endpoint_is_exposed_once_in_openapi(self) -> None:
        paths = server.app.openapi()["paths"]
        path = "/api/v1/me/shift-change-requests/{request_id}/attachment"
        self.assertIn(path, paths)
        self.assertEqual(sorted(paths[path]), ["get", "post"])
        operation_id = str(paths[path]["post"].get("operationId") or "")
        self.assertTrue(operation_id.startswith("upload_shift_request_attachment"), operation_id)


if __name__ == "__main__":
    unittest.main()
