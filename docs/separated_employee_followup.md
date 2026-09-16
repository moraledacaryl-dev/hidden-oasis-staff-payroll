# Separated employee forward-state cleanup

Payroll generation now treats `Inactive`, `Terminated`, `Resigned`, and `Separated` as non-payroll statuses through the canonical status policy.

The schedule employee picker currently excludes `Inactive`, `Terminated`, and `Resigned` in `api/schedules.py`; `Separated` must remain excluded as part of the schedule-status consistency cleanup. Historical attendance and payroll records must not be deleted solely because an employee separates.
