from pathlib import Path
p=Path('core/payroll_engine.py')
s=p.read_text()
old='''            if base_multiplier > 1.0:
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
new='''            if base_multiplier > 1.0:
                if "Regular Holiday" in day_label:
                    # Regular holiday guarantee: the HOLIDAY PAY component itself is at least
                    # 8 ordinary hours, even if the employee was late or worked less than 8.
                    # Actual worked ordinary hours stay in regular_pay; OT stays in ot_pay.
                    holiday_pay_for_day = round(max(standard_paid_hours * hourly_rate, base_regular_pay * (base_multiplier - 1.0)), 2)
                    result.holiday_pay += holiday_pay_for_day
                    regular_holiday_base_paid_dates.add(str(log["work_date"]))
                    warnings.append(f"{log['work_date']} uses {day_label}; holiday pay is at least {standard_paid_hours:g} hours.")
                else:
                    # Special holiday/rest-day premiums remain based on actual paid regular hours.
                    result.holiday_pay += round(base_regular_pay * (base_multiplier - 1.0), 2)
                    warnings.append(f"{log['work_date']} uses {day_label} multiplier {base_multiplier:.2f}x.")
'''
if old not in s:
    raise SystemExit('Expected previous regular holiday minimum block was not found. Run git diff and inspect core/payroll_engine.py around base_multiplier.')
s=s.replace(old,new,1)
p.write_text(s)
print('patched regular holiday holiday_pay column minimum 8 hours')
