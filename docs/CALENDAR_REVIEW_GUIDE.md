# Calendar Review Guide

Calendar Review is the Streamlit prototype version of a Sling-style weekly schedule-vs-actual review page.

## What it adds

- Employee rows
- Seven day columns
- Schedule and actual time log in the same cell
- Color-coded status cards
- Department filter
- Exception filters
- Click/select employee + date editor
- Edit schedule
- Edit actual log
- Mark absent
- Mark SIL / Sick Leave
- Mark reviewed
- Copy schedule to actual

## Why this is not full Sling yet

Streamlit can support review grids and correction forms well, but true browser-native drag-and-drop scheduling belongs in the final Next.js version.

The final Next.js/FastAPI version should add:

- drag shift to another employee/day
- resize shift duration
- copy week
- publish/unpublish schedule
- conflict warnings
- undo
- audit logs per drag/edit
- better mobile/touch behavior

## How to enable in this prototype

Run:

```bash
cd /root/repos/hidden-oasis-staff-payroll
git pull
.venv/bin/python scripts/patch_calendar_review.py
```

Then commit the modified `app.py` if you want the patched app.py stored in Git:

```bash
git add app.py core/calendar_review.py scripts/patch_calendar_review.py docs/CALENDAR_REVIEW_GUIDE.md
git commit -m "Add calendar review page"
git push
```

Restart Streamlit:

```bash
pkill -f "streamlit run app.py"
.venv/bin/streamlit run app.py
```
