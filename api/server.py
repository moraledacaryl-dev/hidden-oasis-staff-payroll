from __future__ import annotations

from api.attendance_compliance import router as attendance_compliance_router
from api.cash_advance_corrections import router as cash_advance_corrections_router
from api.cash_advances import router as cash_advances_router
from api.cash_repayments import router as cash_repayments_router
from api.employees import router as employees_router
from api.hr_records import router as hr_records_router
from api.main import app, configured_db_path
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
from api.payroll_revision_workflow import router as revision_workflow_router
from api.payslip_distribution import router as payslip_distribution_router
from api.performance_reviews import router as performance_reviews_router
from api.production_health import router as production_health_router
from api.schedule_actuals import router as schedule_actuals_router
from api.schedule_change_log import ensure_schedule_change_log_schema
from api.schedule_leave_statuses import router as schedule_leave_statuses_router
from api.schedule_migration import router as schedule_migration_router
from api.schedule_publication import router as schedule_publication_router
from api.schedule_rest_days import router as schedule_rest_days_router
from api.schedules import ensure_schema as ensure_schedule_schema
from api.schedules import router as schedules_router
from api.sil_leave import router as sil_leave_router
from api.staff_published_portal import router as staff_published_portal_router
from api.staff_self_service import router as staff_self_service_router
from api.users import router as users_router
from api.payroll_revision_service import ensure_workflow_schema
from core.db import get_conn, init_db
from core.runtime_guard import validate_runtime_environment


@app.on_event("startup")
def initialize_runtime() -> None:
    validate_runtime_environment()
    conn = get_conn(configured_db_path())
    try:
        init_db(conn)
        ensure_schedule_schema(conn)
        ensure_schedule_change_log_schema(conn)
        ensure_workflow_schema(conn)
        conn.commit()
    finally:
        conn.close()


ROUTERS = (
    payroll_drafts_router,
    payroll_return_router,
    payroll_review_router,
    my_payroll_router,
    payroll_mark_paid_router,
    payroll_corrections_router,
    payroll_audit_events_router,
    schedule_migration_router,
    revision_controls_router,
    revision_workflow_router,
    production_health_router,
    hr_records_router,
    payslip_distribution_router,
    schedules_router,
    schedule_actuals_router,
    schedule_rest_days_router,
    schedule_leave_statuses_router,
    sil_leave_router,
    users_router,
    employees_router,
    schedule_publication_router,
    staff_self_service_router,
    staff_published_portal_router,
    attendance_compliance_router,
    cash_advances_router,
    cash_repayments_router,
    cash_advance_corrections_router,
    performance_reviews_router,
    payroll_adjustments_router,
    payroll_recalculate_router,
)

for router in ROUTERS:
    app.include_router(router)
