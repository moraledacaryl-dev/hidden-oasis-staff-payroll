from __future__ import annotations


INACTIVE_EMPLOYEE_STATUSES = frozenset({"inactive", "terminated", "resigned", "separated"})


def is_active_employee_status(value: object) -> bool:
    return str(value or "active").strip().lower() not in INACTIVE_EMPLOYEE_STATUSES
