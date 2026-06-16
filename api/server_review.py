from __future__ import annotations

from api.main import app
from api.payroll_drafts import router as payroll_drafts_router
from api.payroll_return import router as payroll_return_router
from api.payroll_review import router as payroll_review_router

app.include_router(payroll_drafts_router)
app.include_router(payroll_return_router)
app.include_router(payroll_review_router)
