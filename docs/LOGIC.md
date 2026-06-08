# Payroll Logic Notes

## Core payroll philosophy

Raw logs are not payroll. Payroll uses approved/reviewed attendance.

```text
Biometric/Manual Logs
→ Attendance Review
→ Approved OT / corrections / leave classification
→ Draft Payroll
→ Owner/Manager Review
→ Approved/Paid/Locked Payroll
```

## Payroll basis

Most employees are paid by actual approved hours worked.

```text
Regular Pay = approved regular hours × hourly rate
OT Pay = approved OT hours × hourly rate × OT multiplier
Night Differential = ND hours × hourly rate × ND rate
```

Default settings:

```text
Standard paid hours/day = 8
Standard shift length = 9
Unpaid break = 60 minutes
Night differential = 10 PM to 6 AM
ND rate = 10%
OT rate = 125%
```

## SSS method

Preserve actual month-to-date catch-up method.

```text
Cutoff 1:
SSS basis = actual gross from 1–15
SSS deduction = SSS table employee share for basis

Cutoff 2:
SSS basis = actual gross from 1–end
SSS deduction = full-month SSS employee share − first-cutoff SSS already deducted
```

## PhilHealth and Pag-IBIG

Declared monthly basis by default.

```text
Cutoff 1 = half of monthly employee share
Cutoff 2 = monthly employee share − amount already deducted in cutoff 1
```

## Leaves

Leaves are configurable at settings level and entitlement is set per employee.

Examples:

- Service Incentive Leave
- Sick Leave
- Vacation Leave
- Emergency Leave
- Bereavement Leave
- Unpaid Leave
- Maternity Leave
- Paternity Leave
- Solo Parent Leave
- VAWC Leave
- Special Leave for Women
- AWOL
- Suspension

## Cash advances

Cash advance should be one official record.

```text
Cash advance approval/release
→ Employee receivable
→ Drawer/bank cash out if released
→ Payroll deduction later
→ Outstanding balance reduced
```

## Freelancers

Freelancers can be paid manually by approved outputs.

```text
Payable = approved quantity × rate per output type
```

No benefits are enabled by default for freelance/output-based workers.
