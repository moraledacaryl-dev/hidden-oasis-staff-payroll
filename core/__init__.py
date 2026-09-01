"""Core package policy bindings for Hidden Oasis Staff Payroll."""

# ``core.db.now_iso`` is imported throughout the application. Bind that legacy
# compatibility name to the central aware-UTC serializer so existing callers
# acquire correct timestamp semantics without rewriting payroll business logic.
# The next schema-consolidation pass can move this binding directly into db.py
# once the runtime schema module is refactored.
from . import db as _db
from .observability import utc_storage_iso

_db.now_iso = utc_storage_iso

# Legacy payroll_engine still allocates regular hours by calendar day. Hidden
# Oasis treats distinct same-day scheduled_shift_id values as separate shifts,
# so install the bounded compatibility correction at the engine boundary.
from .independent_shift_payroll import install as _install_independent_shift_payroll

_install_independent_shift_payroll()
