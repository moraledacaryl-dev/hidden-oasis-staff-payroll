# Group 14 — Security and data-protection hardening

## Issues addressed

### 1. Spreadsheet formula injection in payroll and attendance CSVs

Original download routes escaped CSV delimiters and quotes, but untrusted employee names, notes, and correction reasons could start with spreadsheet formulas (including leading whitespace). Quoting a CSV field does **not** always prevent spreadsheet software from evaluating such cells.

The shared `apps/web/lib/csv-security.mjs` encoder now prefixes a literal apostrophe to risky **string** cells, including leading control characters, `=`, `+`, `-` and `@`; commas, quotes, CR, and LF are escaped. Genuine numeric payroll amounts remain numeric. Node's built-in test runner verifies malicious and ordinary samples in CI.

Download endpoints explicitly check the authenticated web session and expected roles **before** reading employee records. Backend API authorization remains a second, independent enforcement layer:
- Payroll CSV items, correction and departmental summary: **Owner / Payroll Admin**
- Attendance template download: **Owner / Payroll Admin / General Manager**
- Staff without those roles and unauthenticated clients: **403 / 401** respectively.

Sensitive CSV responses now use `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`, and attachment disposition. Malformed payroll IDs and unsupported export types fail closed; invalid attendance dates/durations return 400 instead of silently accepting potentially misleading values.

### 2. Inconsistent separated-employee status checks

Certain staff payroll/self-service reads considered only exact `Inactive` status as ineligible; owner impersonation checks denied `Inactive` and `Terminated` but not `Resigned` or `Separated`. All now use `core.active_employee_status.is_active_employee_status` for consistent `Inactive`, `Terminated`, `Resigned`, `Separated` handling, without blocking legitimately `On Leave` staff.

Tests verify employee-linked payroll isolation, forged employee ID rejection, deactivated/unlinked accounts, separated-employee access denial, on-leave eligibility and Owner impersonation restrictions.

## Verification and limitations

- Run `python -m unittest discover -v`, `npm --prefix apps/web run test:security`, full CI lint/typecheck/build and browser smoke.
- Audit scope includes high-value boundaries above and review of existing MFA, token revocation, session impersonation, object ownership and attachment path controls. It is **not** a penetration test of public infrastructure nor an independent statutory/financial certification.
- Do not alter historical Paid payroll, Accounting posting, user secrets, real employee data, or production configuration.
- Production release only after exact-SHA green CI and existing backup/rollback/health-gated deployment.
