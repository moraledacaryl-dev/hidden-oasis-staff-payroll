from pathlib import Path
p=Path('core/payroll_engine.py')
s=p.read_text()
s=s.replace('        approved_leave_dates = set()\n        leave_rows = fetchall(\n','        approved_leave_dates = set()\n        paid_leave_dates = set()\n        leave_rows = fetchall(\n',1)
a=s.index('            overlap_calendar_days = 0')
b=s.index('        for work_date, sched in sched_by_date.items():', a)
replacement='''            overlap_dates = []
            d = overlap_start
            while d <= overlap_end:
                d_iso = d.isoformat()
                approved_leave_dates.add(d_iso)
                if d_iso not in paid_leave_dates:
                    overlap_dates.append(d_iso)
                d += timedelta(days=1)
            paid_days_in_cutoff = float(len(overlap_dates))
            if int(lr.get("paid") or 0) and paid_days_in_cutoff > 0:
                if not ent or not int(ent.get("entitled") or 0):
                    warnings.append(f"Approved paid leave '{lr['leave_name']}' exists but employee entitlement is not enabled.")
                elif float(ent.get("used") or 0) > float(ent.get("credits") or 0) + 0.001:
                    warnings.append(f"Leave '{lr['leave_name']}' usage exceeds configured credits.")
                else:
                    for d_iso in overlap_dates:
                        paid_leave_dates.add(d_iso)
                    result.paid_leave_days += paid_days_in_cutoff
                    result.paid_leave_pay += paid_days_in_cutoff * standard_paid_hours * hourly_rate
                    warnings.append(f"Paid leave '{lr['leave_name']}' pays {paid_days_in_cutoff:g} unique day(s) x {standard_paid_hours:g} standard hours.")

'''
s=s[:a]+replacement+s[b:]
if 'result.paid_leave_pay = round(result.paid_leave_pay, 2)' not in s:
    s=s.replace('        result.holiday_pay = round(result.holiday_pay, 2)\n','        result.holiday_pay = round(result.holiday_pay, 2)\n        result.paid_leave_pay = round(result.paid_leave_pay, 2)\n',1)
p.write_text(s)
print('patched leave unique dates')
