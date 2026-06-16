from __future__ import annotations

from api.main import app
from api.payroll_drafts import router as payroll_drafts_router

app.include_router(payroll_drafts_router)
