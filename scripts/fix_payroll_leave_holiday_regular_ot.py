from pathlib import Path

p = Path('core/payroll_engine.py')
s = p.read_text()

# 1) Payroll rule: inside-schedule hours beyond 8 are OT; outside-schedule paid only if approved.
old_12 = '''            comp = compute_overlap(s_start, s_end, log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins)
            paid_actual = comp["paid_actual_hours"]

            # Hidden Oasis payroll rule:
            # 1) Paid hours are limited to the scheduled window.
            # 2) Outside-schedule early/late time is paid only when approved as OT.
            # 3) Inside-schedule paid time beyond 12 hours is automatically OT.
            inside_schedule_paid = round(float(comp.get("worked_inside_schedule_hours") or 0), 4)
            outside_schedule_paid = round(max(0.0, paid_actual - inside_schedule_paid), 4)
            approved_ot = float(log.get("approved_ot_hours") or 0)
            inside_schedule_ot_threshold = float(get_setting(conn, "inside_schedule_ot_threshold_hours", "12") or 12)

            auto_inside_schedule_ot = round(max(0.0, inside_schedule_paid - inside_schedule_ot_threshold), 4)
            regular_hours = round(min(inside_schedule_paid, inside_schedule_ot_threshold), 4)
            approved_outside_schedule_ot = round(min(approved_ot, outside_schedule_paid), 4)
            detected_extra = round(auto_inside_schedule_ot + outside_schedule_paid, 4)
            payable_ot = round(auto_inside_schedule_ot + approved_outside_schedule_ot, 4)

            # Safety guard: regular + paid OT must never exceed actual paid worked hours.
            if regular_hours + payable_ot > paid_actual + 0.0001:
                payable_ot = round(max(0.0, paid_actual - regular_hours), 4)

            if auto_inside_schedule_ot > 0:
                warnings.append(f"Inside-schedule hours beyond {inside_schedule_ot_threshold:g} on {log['work_date']} were paid as OT.")
            if outside_schedule_paid > 0 and approved_ot <= 0:
                warnings.append(f"Unapproved outside-schedule time on {log['work_date']} was detected but not paid as OT.")
            elif approved_ot > outside_schedule_paid + 0.01:
                warnings.append(f"Approved OT on {log['work_date']} exceeds outside-schedule worked time; payroll uses worked outside-schedule OT only.")
'''
old_approved_only = '''            comp = compute_overlap(s_start, s_end, log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins)
            paid_actual = comp["paid_actual_hours"]

            # Hidden Oasis payroll rule:
            # regular paid hours come only from actual work inside the scheduled window.
            # Early arrivals and late outs are not paid unless approved as OT.
            inside_schedule_paid = round(float(comp.get("worked_inside_schedule_hours") or 0), 4)
            outside_schedule_paid = round(max(0.0, paid_actual - inside_schedule_paid), 4)
            approved_ot = float(log.get("approved_ot_hours") or 0)

            regular_hours = round(min(standard_paid_hours, inside_schedule_paid), 4)
            detected_extra = outside_schedule_paid
            payable_ot = round(min(approved_ot, outside_schedule_paid), 4)

            # Safety guard: regular + paid OT must never exceed actual paid worked hours.
            if regular_hours + payable_ot > paid_actual + 0.0001:
                payable_ot = round(max(0.0, paid_actual - regular_hours), 4)

            if outside_schedule_paid > 0 and approved_ot <= 0:
                warnings.append(f"Unapproved outside-schedule time on {log['work_date']} was detected but not paid as OT.")
            elif approved_ot > outside_schedule_paid + 0.01:
                warnings.append(f"Approved OT on {log['work_date']} exceeds outside-schedule worked time; payroll uses worked outside-schedule OT only.")
'''
new_rule = '''            comp = compute_overlap(s_start, s_end, log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins)
            paid_actual = comp["paid_actual_hours"]

            # Hidden Oasis payroll rule:
            # 1) Paid hours are limited to actual work inside the scheduled window.
            # 2) Inside-schedule paid hours beyond the standard paid day (default 8) are OT.
            # 3) Outside-schedule early/late time is paid only when approved as OT.
            inside_schedule_paid = round(float(comp.get("worked_inside_schedule_hours") or 0), 4)
            outside_schedule_paid = round(max(0.0, paid_actual - inside_schedule_paid), 4)
            approved_ot = float(log.get("approved_ot_hours") or 0)

            auto_inside_schedule_ot = round(max(0.0, inside_schedule_paid - standard_paid_hours), 4)
            regular_hours = round(min(standard_paid_hours, inside_schedule_paid), 4)
            approved_outside_schedule_ot = round(min(approved_ot, outside_schedule_paid), 4)
            detected_extra = round(auto_inside_schedule_ot + outside_schedule_paid, 4)
            payable_ot = round(auto_inside_schedule_ot + approved_outside_schedule_ot, 4)

            # Safety guard: regular + paid OT must never exceed actual paid worked hours.
            if regular_hours + payable_ot > paid_actual + 0.0001:
                payable_ot = round(max(0.0, paid_actual - regular_hours), 4)

            if auto_inside_schedule_ot > 0:
                warnings.append(f"Inside-schedule hours beyond {standard_paid_hours:g} on {log['work_date']} were paid as OT.")
            if outside_schedule_paid > 0 and approved_ot <= 0:
                warnings.append(f"Unapproved outside-schedule time on {log['work_date']} was detected but not paid as OT.")
            elif approved_ot > outside_schedule_paid + 0.01:
                warnings.append(f"Approved OT on {log['work_date']} exceeds outside-schedule worked time; payroll uses worked outside-schedule OT only.")
'''
if old_12 in s:
    s = s.replace(old_12, new_rule, 1)
elif old_approved_only in s:
    s = s.replace(old_approved_only, new_rule, 1)
else:
    print('OT rule block not found or already updated')

# 2) Make paid leave explicit: one paid leave day = standard paid hours x hourly rate.
old_leave = '''                result.paid_leave_days += paid_days_in_cutoff
                result.paid_leave_pay += paid_days_in_cutoff * standard_paid_hours * hourly_rate
'''
new_leave = '''                result.paid_leave_days += paid_days_in_cutoff
                leave_pay = paid_days_in_cutoff * standard_paid_hours * hourly_rate
                result.paid_leave_pay += leave_pay
                warnings.append(f"Paid leave '{lr['leave_name']}' on {lr['start_date']} pays {paid_days_in_cutoff:g} day(s) x {standard_paid_hours:g} standard hours.")
'''
if old_leave in s:
    s = s.replace(old_leave, new_leave, 1)
else:
    print('leave pay block not found or already updated')

# 3) Round paid leave pay after loop.
old_rounds = '''        result.holiday_pay = round(result.holiday_pay, 2)
'''
new_rounds = '''        result.holiday_pay = round(result.holiday_pay, 2)
        result.paid_leave_pay = round(result.paid_leave_pay, 2)
'''
if old_rounds in s and 'result.paid_leave_pay = round(result.paid_leave_pay, 2)' not in s:
    s = s.replace(old_rounds, new_rounds, 1)

p.write_text(s)
print('Patched payroll rules: inside scheduled hours over 8 are OT, leave pay is standard day pay, and leave pay rounds.')
