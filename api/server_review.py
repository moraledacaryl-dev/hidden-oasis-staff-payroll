from __future__ import annotations

from api.main import app
from api.payroll_drafts import router as payroll_drafts_router
from api.payroll_return import router as payroll_return_router
from api.payroll_review import router as payroll_review_router
from api.my_payroll import router as my_payroll_router
from api.payroll_mark_paid import router as payroll_mark_paid_router
from api.payroll_corrections import router as payroll_corrections_router
from api.payroll_audit_events import router as payroll_audit_events_router
from api.payroll_revision_controls import router as revision_controls_router
from api.schedules import router as schedules_router
from api.schedule_actuals import router as schedule_actuals_router
from api.schedule_migration import router as schedule_migration_router
from api.users import router as users_router

app.include_router(payroll_drafts_router)
app.include_router(payroll_return_router)
app.include_router(payroll_review_router)
app.include_router(my_payroll_router)
app.include_router(payroll_mark_paid_router)
app.include_router(payroll_corrections_router)
app.include_router(payroll_audit_events_router)
app.include_router(schedule_migration_router)
app.include_router(revision_controls_router)
app.include_router(schedules_router)
app.include_router(schedule_actuals_router)
app.include_router(users_router)
