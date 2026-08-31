# Master Data and Departments Guide

> Current UI note: the older **Data Import / Templates** workspace described by earlier versions of this guide is not present in the current application navigation. Do not look for a generic “Data Upload” screen. Attendance files are handled through **Operations → Attendance Upload**. Date-specific payroll holidays are managed through **Payroll → Holiday Calendar** using the controlled **Regular Holiday** and **Special Non-Working Day** classifications.

Historical template imports may still exist in old data or operational records, but they are not the current user-facing workflow and should not be treated as a discoverable application feature.

## Employee master data

Employee records should use one stable `employee_code` per person. When importing or synchronizing employee master data through an approved administrative process, use these practical minimum fields:

```text
employee_code
full_name
department
position
employment_type
status
```

Recommended fields:

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

## Holiday configuration

Configure payroll holidays in **Payroll → Holiday Calendar** before previewing or creating payroll for the affected period.

Each holiday record has:

- date
- holiday name
- controlled classification: **Regular Holiday** or **Special Non-Working Day**
- active/inactive status
- optional notes

Inactive holiday records remain visible for auditability but do not affect new payroll calculations. Saved payroll snapshots are not silently rewritten when a holiday source record changes; use the existing controlled recalculation/revision workflow when a source correction must be reflected in payroll.

## Attendance upload

The current upload entry point is **Operations → Attendance Upload**. It is specifically for attendance/time-log workflows and should not be described as a generic master-data or holiday importer.

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
