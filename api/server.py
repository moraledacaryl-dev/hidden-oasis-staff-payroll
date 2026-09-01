from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, FastAPI

import api.main as core_main_module
from api.attendance_compliance import router as attendance_compliance_router
from api.attendance_template_import import router as attendance_template_import_router
from api.attendance_template_split_shift import router as attendance_template_split_shift_router
from api.cash_advance_corrections import router as cash_advance_corrections_router
from api.cash_advances import router as cash_advances_router
from api.cash_repayments import router as cash_repayments_router
from api.employees import router as employees_router
from api.holidays import router as holidays_router
from api.hr_records import router as hr_records_router
from api.impersonation import router as impersonation_router
from api.integrations import router as integrations_router
from api.main import (
    API_PREFIX,
    PayrollPreviewRequest,
    build_app as build_core_app,
    configured_db_path,
    db_conn,
    parse_date_order,
    payroll_result_to_api,
)
from api.my_payroll import router as my_payroll_router
from api.payroll_adjustments import router as payroll_adjustments_router
from api.payroll_audit_events import router as payroll_audit_events_router
from api.payroll_corrections import router as payroll_corrections_router
from api.payroll_drafts import router as payroll_drafts_router
from api.payroll_mark_paid import router as payroll_mark_paid_router
from api.payroll_recalculate import router as payroll_recalculate_router
from api.payroll_return import router as payroll_return_router
from api.payroll_review import router as payroll_review_router
from api.payroll_revision_controls import router as revision_controls_router
from api.payroll_revision_service import ensure_workflow_schema
from api.payroll_revision_workflow import router as revision_workflow_router
from api.payslip_distribution import router as payslip_distribution_router
from api.performance_reviews import router as performance_reviews_router
from api.production_health import router as production_health_router
from api.schedule_actuals import router as schedule_actuals_router
from api.schedule_canonical_runtime import router as schedule_canonical_runtime_router
from api.schedule_change_log import ensure_schedule_change_log_schema
from api.schedule_leave_fractional import router as schedule_leave_fractional_router
from api.schedule_leave_statuses import router as schedule_leave_statuses_router
from api.schedule_migration import router as schedule_migration_router
from api.schedule_publication import router as schedule_publication_router
from api.schedule_rest_days import router as schedule_rest_days_router
from api.schedules import ensure_schema as ensure_schedule_schema
from api.schedules import router as schedules_router
from api.security import ROLE_OWNER, ROLE_PAYROLL, require_api_key, require_roles
from api.sil_leave import router as sil_leave_router
from api.split_shift_actual_reconciliation import reconcile_unlinked_split_shift_logs
from api.staff_published_portal import router as staff_published_portal_router
from api.staff_self_service import router as staff_self_service_router
from api.users import router as users_router
from core.db import get_conn, init_db
from core.integration_compat import ensure_legacy_integration_writer_compatibility
from core.integration_outbox import ensure_integration_schema
from core.observability import utc_storage_iso
from core.payroll_fractional_leave import compute_payroll_with_fractional_leave
from core.quality import build_payroll_preflight_checks, summarize_checks
from core.runtime_guard import validate_runtime_environment

# api.main retains a compatibility-local now_iso helper. The canonical
# production entrypoint binds it to the central aware UTC serializer before
# build_core_app() installs request handlers, preserving old imports while
# eliminating local-time writes. This compatibility binding is intentionally
# removed when api/main.py is decomposed in the schema-consolidation pass.
core_main_module.now_iso = utc_storage_iso


def initialize_runtime() -> None:
    validate_runtime_environment()
    conn = get_conn(configured_db_path())
    try:
        init_db(conn)
        ensure_schedule_schema(conn)
        ensure_schedule_change_log_schema(conn)
        ensure_workflow_schema(conn)
        ensure_integration_schema(conn)
        ensure_legacy_integration_writer_compatibility(conn)
        reconcile_unlinked_split_shift_logs(conn)
        conn.commit()
    finally:
        conn.close()


@asynccontextmanager
async def application_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize runtime state before the application accepts traffic."""
    initialize_runtime()
    yield


def payroll_preview_fractional(
    payload: PayrollPreviewRequest,
    user: dict[str, Any] = Depends(require_roles(ROLE_OWNER, ROLE_PAYROLL)),
) -> dict[str, Any]:
    start, end = parse_date_order(payload.period_start, payload.period_end)
    with db_conn(read_only=True) as conn:
        checks = build_payroll_preflight_checks(conn, start, end)
        results = [
            payroll_result_to_api(item)
            for item in compute_payroll_with_fractional_leave(conn, start, end)
        ]
    totals = {
        "employees": len(results),
        "gross_pay": round(sum(float(row.get("gross_pay") or 0) for row in results), 2),
        "net_pay": round(sum(float(row.get("net_pay") or 0) for row in results), 2),
        "total_deductions": round(
            sum(float(row.get("total_deductions") or 0) for row in results), 2
        ),
        "cash_advance_deduction": round(
            sum(float(row.get("cash_advance_deduction") or 0) for row in results), 2
        ),
    }
    return {
        "period_start": start,
        "period_end": end,
        "summary": summarize_checks(checks),
        "checks": checks,
        "totals": totals,
        "items": results,
        "mode": "preview_only_no_save",
    }


def _route_key(route: Any) -> tuple[str, str] | None:
    methods = getattr(route, "methods", None)
    path = getattr(route, "path", None)
    if not path or not methods:
        return None
    return str(path), ",".join(sorted(str(method).upper() for method in methods))


def _walk_routes(routes: list[Any]) -> list[Any]:
    result: list[Any] = []
    for route in routes:
        result.append(route)
        nested = getattr(route, "routes", None)
        if nested:
            result.extend(_walk_routes(list(nested)))
    return result


def _route_method_keys(route: Any) -> list[tuple[str, str]]:
    path = getattr(route, "path", None)
    methods = getattr(route, "methods", None)
    if not path or not methods:
        return []
    return [(str(path), str(method).upper()) for method in methods]


def _route_endpoint_name(route: Any) -> str:
    endpoint = getattr(route, "endpoint", None)
    return getattr(endpoint, "__name__", repr(endpoint))


def assert_unique_route_registry(application: FastAPI) -> None:
    """Fail fast when two active routes claim the same path and HTTP method."""
    by_method: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in _walk_routes(list(application.router.routes)):
        for key in _route_method_keys(route):
            by_method[key].append(_route_endpoint_name(route))

    duplicates = {
        key: endpoints for key, endpoints in by_method.items() if len(endpoints) > 1
    }
    if not duplicates:
        return

    details = "; ".join(
        f"{method} {path} -> {', '.join(endpoints)}"
        for (path, method), endpoints in sorted(duplicates.items())
    )
    raise RuntimeError(f"Duplicate API route registrations detected: {details}")


def _include_router_filtered(
    application: FastAPI,
    source: APIRouter,
    excluded: set[tuple[str, str]],
) -> None:
    """Include a router without mutating the imported router object."""
    filtered = APIRouter()
    filtered.routes.extend(
        route for route in source.routes if _route_key(route) not in excluded
    )
    application.include_router(filtered)


# payroll_revision_controls nests the legacy schedule-history router. Keep its
# historical move/delete handlers, but never register the obsolete employee-day
# scheduled/actual writers: they ignore shift_id and can overwrite an unlinked
# attendance row on split-shift days. Canonical shift-aware writers live in
# api/schedules.py and must be the sole dispatch owners for these two routes.
REVISION_CONTROLS_EXCLUDED_ROUTES = {
    (f"{API_PREFIX}/schedules/day/scheduled", "POST"),
    (f"{API_PREFIX}/schedules/day/actual", "POST"),
}

SCHEDULES_EXCLUDED_ROUTES = {
    (f"{API_PREFIX}/schedules/day/leave", "POST"),
    (f"{API_PREFIX}/schedules/shifts/{{shift_id}}/delete", "POST"),
    (f"{API_PREFIX}/schedules/shifts/{{shift_id}}/move", "POST"),
    (f"{API_PREFIX}/schedules/week", "GET"),
}

ROUTERS = (
    impersonation_router,
    payroll_drafts_router,
    payroll_return_router,
    payroll_review_router,
    my_payroll_router,
    payroll_mark_paid_router,
    payroll_corrections_router,
    payroll_audit_events_router,
    schedule_migration_router,
    revision_workflow_router,
    production_health_router,
    hr_records_router,
    payslip_distribution_router,
    schedule_leave_fractional_router,
    schedule_actuals_router,
    schedule_rest_days_router,
    schedule_leave_statuses_router,
    sil_leave_router,
    users_router,
    employees_router,
    holidays_router,
    integrations_router,
    schedule_publication_router,
    schedule_canonical_runtime_router,
    staff_published_portal_router,
    attendance_compliance_router,
    attendance_template_import_router,
    attendance_template_split_shift_router,
    cash_advances_router,
    cash_repayments_router,
    cash_advance_corrections_router,
    performance_reviews_router,
    payroll_adjustments_router,
    payroll_recalculate_router,
)

LEGACY_MAIN_OVERRIDES = {
    (f"{API_PREFIX}/schedules/day/scheduled", "POST"),
    (f"{API_PREFIX}/schedules/day/actual", "POST"),
    (f"{API_PREFIX}/schedules/day/leave", "POST"),
}


def _remove_superseded_routes(application: FastAPI) -> None:
    application.router.routes = [
        route
        for route in application.router.routes
        if not (
            getattr(route, "path", "") == f"{API_PREFIX}/payroll/preview"
            and "POST" in getattr(route, "methods", set())
        )
        and not any(
            getattr(route, "path", "") == path
            and method in getattr(route, "methods", set())
            for path, method in LEGACY_MAIN_OVERRIDES
        )
    ]


def create_app() -> FastAPI:
    """Build a fully configured, isolated Staff Payroll API application."""
    application = build_core_app()
    application.router.lifespan_context = application_lifespan

    _remove_superseded_routes(application)
    application.add_api_route(
        f"{API_PREFIX}/payroll/preview",
        payroll_preview_fractional,
        methods=["POST"],
        dependencies=[Depends(require_api_key)],
    )

    for router in ROUTERS:
        application.include_router(router)

    _include_router_filtered(
        application,
        revision_controls_router,
        REVISION_CONTROLS_EXCLUDED_ROUTES,
    )
    _include_router_filtered(application, schedules_router, SCHEDULES_EXCLUDED_ROUTES)
    application.include_router(staff_self_service_router)
    assert_unique_route_registry(application)
    return application


app = create_app()
