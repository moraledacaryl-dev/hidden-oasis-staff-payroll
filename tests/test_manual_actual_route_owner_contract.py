from __future__ import annotations

import api.server as server


def test_manual_actual_dispatch_is_owned_only_by_shift_aware_handler() -> None:
    """Starlette dispatches the first matching route, so OpenAPI alone is insufficient."""
    matches = []
    for route in server.app.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set()) or set()
        if path == "/api/v1/schedules/day/actual" and "POST" in methods:
            endpoint = getattr(route, "endpoint", None)
            matches.append(getattr(endpoint, "__name__", repr(endpoint)))

    assert matches == ["save_day_actual"], matches


def test_manual_schedule_dispatch_is_owned_only_by_shift_aware_handler() -> None:
    matches = []
    for route in server.app.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set()) or set()
        if path == "/api/v1/schedules/day/scheduled" and "POST" in methods:
            endpoint = getattr(route, "endpoint", None)
            matches.append(getattr(endpoint, "__name__", repr(endpoint)))

    assert matches == ["save_day_schedule"], matches
