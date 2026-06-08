# GitHub Push Guide

## Recommended repository name

`hidden-oasis-staff-payroll`

## Push locally

```bash
cd /Users/caryl/Desktop/staff-program
git init
.venv/bin/python -m unittest discover
.venv/bin/python smoke_test.py
git add .
git commit -m "Initial Staff Payroll prototype"
git branch -M main
git remote add origin https://github.com/moraledacaryl-dev/hidden-oasis-staff-payroll.git
git push -u origin main
```

## Before pushing

Use `docs/GITHUB_MIGRATION_CHECKLIST.md`.

Confirm these are **not** committed:

- `data/staff_payroll.sqlite`
- `.venv/`
- `__pycache__/`
- generated ZIP/PDF exports
- local secrets

Recommended GitHub visibility while payroll logic and integrations are still being refined: **Private**.

## After pushing

Create one workspace containing:

- `accounting-program-online`
- `pos-cloud-online`
- `operations-command-center`
- `hidden-oasis-staff-payroll`

Then run Codex using `docs/CODEX_PROMPT_OTHER_APPS.md`.
