# Master Data and Departments Guide

Use master data imports for employee setup whenever possible. Do not manually add every employee if you already have a complete list.

## Upload order

1. Download the Required Templates workbook in **Data Import / Templates**.
2. Fill the **Employees** sheet first.
3. Fill optional master/setup sheets, if needed:
   - LeaveTypes
   - LeaveEntitlements
   - AppUsers
   - Holidays
   - FreelanceRates
4. Upload the filled workbook in **Data Import / Templates > Import filled template**.
5. Then upload schedules and time logs using the Schedules and TimeLogs sheets.

## Employees sheet minimum columns

Required practical minimum:

```text
employee_code
full_name
department
position
employment_type
status
```

Recommended columns:

```text
hourly_rate
daily_rate
declared_monthly_base
standard_shift_hours
unpaid_break_minutes
security_no_break
benefits_sss
benefits_philhealth
benefits_pagibig
benefits_tax
start_date
regularization_date
supervisor
emergency_contact
notes
```

The importer matches existing employees using `employee_code`. Re-uploading the same employee code updates the employee instead of creating another employee.

## Department rules

Use one standard department list. Suggested starter list:

```text
Reception
Housekeeping
Kitchen
Cafe
Security
Admin
Freelance
Maintenance
Marketing
Management
```

Avoid spelling variants because these names are used later by Operations and the Staff App:

```text
Cafe vs Café
Kitchen Cafe vs Cafe
Front Desk vs Reception
HK vs Housekeeping
```

## Department UI rule

Department should be selected from a dropdown in:

- Add Employee
- Edit Employee
- Add Schedule
- Imports and sync checks

New departments should be created in **Settings > Departments**, then reused everywhere.

## Operations sync boundary

Safe to sync to Operations:

- employee_code
- full_name/display_name
- department
- position
- status
- review/pending counts

Keep inside Staff/Payroll:

- pay rates
- government numbers
- detailed payroll lines
- private HR notes
- detailed annual review content
