from pathlib import Path

p = Path('core/payroll_engine.py')
s = p.read_text()

needle = '''        for work_date, sched in sched_by_date.items():
            if work_date in regular_holidays:
                continue
'''
insert = '''        for hol_date in regular_holidays:
            if hol_date in regular_holiday_base_paid_dates or hol_date in log_dates or hol_date in approved_leave_dates:
                continue
            result.holiday_pay += standard_paid_hours * hourly_rate
            regular_holiday_base_paid_dates.add(hol_date)
            warnings.append(f"Regular holiday base pay on {hol_date} was paid even with no worked log.")

'''

if insert.strip() not in s:
    if needle not in s:
        raise SystemExit('Regular holiday insertion point not found.')
    s = s.replace(needle, insert + needle, 1)

p.write_text(s)
print('patched regular holiday base pay')
