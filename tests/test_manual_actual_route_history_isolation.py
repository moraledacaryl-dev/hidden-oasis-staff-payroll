from __future__ import annotations

import api.payroll_revision_controls as revision_controls


def test_revision_controls_still_exposes_history_move_delete_but_not_day_writers() -> None:
    paths = {
        (getattr(route, "path", ""), method)
        for route in revision_controls.router.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    assert ("/api/v1/schedules/shifts/{shift_id}/move", "POST") in paths
    assert ("/api/v1/schedules/shifts/{shift_id}/delete", "POST") in paths
    # These nested routes remain present on the source router for compatibility;
    # api.server filters them before application registration.
    assert ("/api/v1/schedules/day/actual", "POST") in paths
