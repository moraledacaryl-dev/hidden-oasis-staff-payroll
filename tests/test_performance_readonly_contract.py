from __future__ import annotations

import inspect

import api.performance_reviews_runtime as runtime
import api.server as server


def test_performance_get_handlers_are_schema_and_commit_free() -> None:
    annual_source = inspect.getsource(runtime.list_annual_reviews_readonly)
    logs_source = inspect.getsource(runtime.list_performance_logs_readonly)

    for source in (annual_source, logs_source):
        assert "ensure_schema(" not in source
        assert "ensure_performance_logs_schema(" not in source
        assert ".commit(" not in source
        assert "CREATE TABLE" not in source
        assert "ALTER TABLE" not in source
        assert "CREATE INDEX" not in source


def test_runtime_initializes_both_performance_schema_families() -> None:
    source = inspect.getsource(server.initialize_runtime)
    assert "ensure_performance_review_schema(conn)" in source
    assert "ensure_performance_logs_schema(conn)" in source


def test_runtime_router_owns_one_get_for_each_performance_surface() -> None:
    route_methods = [
        (getattr(route, "path", ""), set(getattr(route, "methods", set())))
        for route in runtime.router.routes
    ]
    assert sum(
        path == "/api/v1/performance/annual-reviews" and "GET" in methods
        for path, methods in route_methods
    ) == 1
    assert sum(
        path == "/api/v1/performance/logs" and "GET" in methods
        for path, methods in route_methods
    ) == 1


def test_legacy_performance_write_routes_are_retained() -> None:
    route_methods = [
        (getattr(route, "path", ""), set(getattr(route, "methods", set())))
        for route in runtime.router.routes
    ]
    assert any(
        path == "/api/v1/performance/annual-reviews" and "POST" in methods
        for path, methods in route_methods
    )
    assert any(
        path == "/api/v1/performance/logs" and "POST" in methods
        for path, methods in route_methods
    )
