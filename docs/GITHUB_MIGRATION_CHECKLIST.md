# GitHub Migration Checklist

Use this checklist before pushing the Staff/Payroll prototype to GitHub.

## 1. Local Verification

Run from the project folder:

```bash
.venv/bin/python -m unittest discover
.venv/bin/python smoke_test.py
PYTHONPYCACHEPREFIX=/tmp/staff-program-pycache .venv/bin/python -m py_compile app.py core/*.py smoke_test.py tests/*.py
```

If you are not using the local `.venv`, use `python3` instead.

## 2. Confirm Local Files Stay Out Of Git

These must not be committed:

- `.venv/`
- `.env`
- `.streamlit/secrets.toml`
- `data/staff_payroll.sqlite`
- `data/*.db`
- generated ZIP/PDF/Excel exports
- uploaded payroll/import files

The repository should include `data/.gitkeep` so the runtime data folder exists after clone.

## 3. First Login After Clone

The app seeds demo users for a fresh local database. Existing active users without passwords receive this temporary password:

```text
ChangeMe123!
```

The app forces a password change before continuing. Owner users can create/reset users in **Access Control**.

## 4. GitHub Repository Settings

Recommended repository:

```text
hidden-oasis-staff-payroll
```

Recommended visibility while payroll logic is still being refined:

```text
Private
```

Add a repository description:

```text
Hidden Oasis Staff, Attendance, Payroll, Payslip, 13th Month, and Accounting/Operations integration prototype.
```

## 5. Post-Push Workspace

Use this repository beside:

- `accounting-program-online`
- `pos-cloud-online`
- `operations-command-center`

Then use `docs/CODEX_PROMPT_OTHER_APPS.md` to update the other apps with the Staff/Payroll source-of-truth boundary.

## Still Not Final Production

This local Streamlit build now has login, hashed passwords, sessions, role-restricted pages, guarded payroll approvals, tests, and GitHub-safe ignores.

Before live payroll, still validate:

- official/current SSS table
- official/current withholding-tax assumptions
- final biometric device export format
- direct API transport to Accounting/Operations
- production FastAPI/PostgreSQL/Next.js rebuild path
