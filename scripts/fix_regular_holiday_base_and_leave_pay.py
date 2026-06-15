from pathlib import Path

p = Path('core/payroll_engine.py')
s = p.read_text()

# Add regular holiday lookup after schedules are loaded.
old = '''        sched_by_date = {s["work_date"]: s for s in scheds}
        log_dates = set()
'''
new = '''        sched_by_date = {s["work_date"]: s for s in scheds}
        holiday_rows = fetchall(
            conn,
            "SELECT * FROM holidays WHERE active=1 AND holiday_date BETWEEN ? AND ?",
            (period_start, period_end),
        )
        regular_holidays = {
            str(h["holiday_date"]): h
            for h in holiday_rows
            if "regular" in str(h.get("holiday_type") or "").lower()
        }
        regular_holiday_base_paid_dates: set[str] = set()
        log_dates = set()
'''
if old not in s:
    raise SystemExit('schedule/holiday insert point not found')
s = s.replace(old, new, 1)

# Regular holiday pays even if absent.
old = '''            if log.get("is_absent"):
                result.unpaid_absence_days += 1
                log_dates.add(log["work_date"])
                continue
'''
new = '''            if log.get("is_absent"):
                work_date = str(log["work_date"])
                if work_date in regular_holidays:
                    result.holiday_pay += standard_paid_hours * hourly_rate
                    regular_holiday_base_paid_dates.add(work_date)
                    warnings.append(f"Regular holiday base pay on {work_date} was paid even though employee was absent.")
                else:
                    result.unpaid_absence_days += 1
                log_dates.add(work_date)
                continue
'''
if old not in s:
    raise SystemExit('absent handling block not found')
s = s.replace(old, new, 1)

# Make leave pay explicit and rounded.
old = '''                result.paid_leave_days += paid_days_in_cutoff
                result.paid_leave_pay += paid_days_in_cutoff * standard_paid_hours * hourly_rate
'''
new = '''                result.paid_leave_days += paid_days_in_cutoff
                leave_pay = paid_days_in_cutoff * standard_paid_hours * hourly_rate
                result.paid_leave_pay += leave_pay
                warnings.append(f"Paid leave '{lr['leave_name']}' pays {paid_days_in_cutoff:g} day(s) x {standard_paid_hours:g} standard hours.")
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    print('leave pay block already updated or not found')

# Insert regular holiday base pay for dates without worked/absent logs after leave dates are known.
old = '''        for work_date, sched in sched_by_date.items():
            if sched.get("is_rest_day"):
                continue
            if work_date not in log_dates and work_date not in approved_leave_dates:
                result.unpaid_absence_days += 1
                warnings.append(f"Scheduled day {work_date} has no time log or approved leave; counted as unpaid absence.")
'''
new = '''        for hol_date, holiday in regular_holidays.items():
            if hol_date in regular_holiday_base_paid_dates or hol_date in log_dates or hol_date in approved_leave_dates:
                continue
            result.holiday_pay += standard_paid_hours * hourly_rate
            regular_holiday_base_paid_dates.add(hol_date)
            warnings.append(f"Regular holiday base pay on {hol_date} was paid even with no worked log.")

        for work_date, sched in sched_by_date.items():
            if work_date in regular_holidays:
                continue
            if sched.get("is_rest_day"):
                continue
            if work_date not in log_dates and work_date not in approved_leave_dates:
                result.unpaid_absence_days += 1
                warnings.append(f"Scheduled day {work_date} has no time log or approved leave; counted as unpaid absence.")
'''
if old not in s:
    raise SystemExit('scheduled day absence block not found')
s = s.replace(old, new, 1)

# Round paid leave too.
old = '''        result.holiday_pay = round(result.holiday_pay, 2)
'''
new = '''        result.holiday_pay = round(result.holiday_pay, 2)
        result.paid_leave_pay = round(result.paid_leave_pay, 2)
'''
if old in s and 'result.paid_leave_pay = round(result.paid_leave_pay, 2)' not in s:
    s = s.replace(old, new, 1)

p.write_text(s)
print('Patched regular holiday base pay and paid leave computation.')
