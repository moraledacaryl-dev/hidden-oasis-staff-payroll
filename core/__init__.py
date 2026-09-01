"""Core package policy bindings for Hidden Oasis Staff Payroll."""

# ``core.db.now_iso`` is imported throughout the application. Bind that legacy
# compatibility name to the central aware-UTC serializer so existing callers
# acquire correct timestamp semantics without rewriting payroll business logic.
# The next schema-consolidation pass can move this binding directly into db.py
# once the runtime schema module is refactored.
from . import db as _db
from .observability import utc_storage_iso

_db.now_iso = utc_storage_iso

# PR #54 introduced the correct independent scheduled-shift payroll policy, but
# legacy callers still import core.payroll_engine.compute_payroll directly.
# Bind that public compute path to the policy once at package initialization.
from .default_payroll_policy import install as _install_default_payroll_policy

_install_default_payroll_policy()
