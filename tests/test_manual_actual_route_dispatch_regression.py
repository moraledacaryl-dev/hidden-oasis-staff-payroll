from __future__ import annotations

import api.server as server


def test_first_post_actual_route_is_shift_aware_writer() -> None:
    matches = [
        route
        for route in server.app.router.routes
        if getattr(route, "path", None) == "/api/v1/schedules/day/actual"
        and "POST" in (getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1
    assert getattr(matches[0].endpoint, "__name__", "") == "save_day_actual"
