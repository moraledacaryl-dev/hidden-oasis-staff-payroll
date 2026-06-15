from pathlib import Path

p = Path('core/payroll_engine.py')
s = p.read_text()

old = '''            comp = compute_overlap(s_start, s_end, log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins)
            paid_actual = comp["paid_actual_hours"]

            # Non-overlapping daily pay-hour split:
            # first standard paid hours are regular; anything beyond that is overtime,
            # even if the longer shift was scheduled.
            regular_hours = round(min(standard_paid_hours, paid_actual), 4)
            detected_extra = round(max(0.0, paid_actual - standard_paid_hours), 4)
            approved_ot = float(log.get("approved_ot_hours") or 0)

            # Payroll should pay all detected hours beyond the standard day as OT.
            # approved_ot_hours is kept for review/audit context, not as a cap that erases payable OT.
            payable_ot = detected_extra

            # Safety guard: regular + OT must never exceed paid actual hours.
            if regular_hours + payable_ot > paid_actual + 0.0001:
                payable_ot = round(max(0.0, paid_actual - regular_hours), 4)

            if detected_extra > 0 and approved_ot <= 0:
                warnings.append(f"Detected OT on {log['work_date']} from paid hours beyond {standard_paid_hours:g}; included in payroll draft.")
            elif approved_ot > detected_extra + 0.01:
                warnings.append(f"Approved OT on {log['work_date']} exceeds detected worked extra time; payroll uses detected worked OT.")
'''

new = '''            comp = compute_overlap(s_start, s_end, log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins)
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

if old not in s:
    raise SystemExit('Expected old payroll actual-hours block not found. Stop and inspect core/payroll_engine.py around compute_overlap.')

s = s.replace(old, new, 1)

# Night differential should not pay more ND hours than payable hours after the new rule.
old_nd = '''            nd = compute_nd_hours(log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins=0)
            result.night_diff_hours += nd
            result.night_diff_pay += nd * hourly_rate * nd_rate * base_multiplier
'''
new_nd = '''            raw_nd = compute_nd_hours(log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins=break_mins)
            payable_hours_for_nd = round(regular_hours + payable_ot, 4)
            nd = round(min(raw_nd, payable_hours_for_nd), 4)
            result.night_diff_hours += nd
            result.night_diff_pay += nd * hourly_rate * nd_rate * base_multiplier
'''
if old_nd in s:
    s = s.replace(old_nd, new_nd, 1)
else:
    print('ND block not found or already changed; skipped ND cap patch')

p.write_text(s)
print('Patched payroll: paid hours limited to scheduled window unless OT is approved.')
