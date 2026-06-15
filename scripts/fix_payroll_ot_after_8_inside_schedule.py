from pathlib import Path

p = Path('core/payroll_engine.py')
s = p.read_text()

old = '''            comp = compute_overlap(s_start, s_end, log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins)
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

new = '''            comp = compute_overlap(s_start, s_end, log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins)
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

if old not in s:
    alt_old = '''            comp = compute_overlap(s_start, s_end, log["work_date"], log.get("actual_in"), log.get("actual_out"), break_mins)
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
    if alt_old not in s:
        raise SystemExit('Expected payroll block not found. Inspect core/payroll_engine.py around compute_overlap.')
    s = s.replace(alt_old, new, 1)
else:
    s = s.replace(old, new, 1)

p.write_text(s)
print('Patched payroll: inside-schedule hours over 8 are OT; outside-schedule requires approval.')
