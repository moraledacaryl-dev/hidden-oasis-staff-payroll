from pathlib import Path

p = Path('core/payroll_engine.py')
s = p.read_text()

old = '''            base_multiplier, day_label = day_pay_multipliers(conn, log["work_date"], is_rest_day)
            base_regular_pay = regular_hours * hourly_rate
            result.regular_hours += regular_hours
            result.regular_pay += base_regular_pay
            if base_multiplier > 1.0:
                # Store only the premium above ordinary pay in holiday_pay so gross = ordinary base + premium.
                result.holiday_pay += round(base_regular_pay * (base_multiplier - 1.0), 2)
                warnings.append(f"{log['work_date']} uses {day_label} multiplier {base_multiplier:.2f}x.")
'''
new = '''            base_multiplier, day_label = day_pay_multipliers(conn, log["work_date"], is_rest_day)
            base_regular_pay = regular_hours * hourly_rate
            result.regular_hours += regular_hours
            result.regular_pay += base_regular_pay
            if base_multiplier > 1.0:
                # Store only the premium above ordinary pay in holiday_pay so gross = ordinary base + premium.
                holiday_premium = round(base_regular_pay * (base_multiplier - 1.0), 2)
                result.holiday_pay += holiday_premium
                warnings.append(f"{log['work_date']} uses {day_label} multiplier {base_multiplier:.2f}x.")

                # Regular holiday guarantee: the employee gets at least 8 ordinary hours of pay
                # for the regular holiday date, even if the worked scheduled hours are below 8.
                if "Regular Holiday" in day_label:
                    regular_holiday_minimum_pay = standard_paid_hours * hourly_rate
                    current_regular_holiday_pay = base_regular_pay + holiday_premium
                    if current_regular_holiday_pay < regular_holiday_minimum_pay:
                        top_up = round(regular_holiday_minimum_pay - current_regular_holiday_pay, 2)
                        result.holiday_pay += top_up
                        warnings.append(f"Regular holiday minimum pay on {log['work_date']} was topped up to {standard_paid_hours:g} hours.")
'''
if old not in s:
    raise SystemExit('holiday worked-pay block not found')
s = s.replace(old, new, 1)
p.write_text(s)
print('patched regular holiday minimum 8 hours')
