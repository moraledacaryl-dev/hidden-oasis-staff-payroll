# V4 Upgrade Notes

V4 upgrades the V3 staff/payroll prototype without removing the V3 modules.

## Added

### 1. Data Import / Templates
- New page: **Data Import / Templates**
- Downloadable required Excel template with sheets for:
  - Employees
  - Schedules
  - TimeLogs
  - LeaveTypes
  - LeaveEntitlements
  - LeaveRequests
  - CashAdvances
  - FreelanceRates
  - FreelanceOutputs
  - PayrollAdjustments
  - Holidays
  - SSS_Table
  - BiometricDaily
  - BiometricTimestamp
- Upload completed template workbook and import it into the app.
- Export a full database snapshot to Excel for backup/review.

### 2. Legacy Payroll ZIP Import
- Upload old `Payroll.zip`, a zip containing `payroll.sqlite`, or a template zip.
- Migrates old app data into the new model:
  - Employees
  - Schedules
  - Time logs
  - Holidays
  - SSS contribution table
  - Other earnings/deductions
  - Payroll history
  - Payroll history lines
  - 13th month records
- Legacy payroll history is imported as **Locked** to preserve history without recomputation.

### 3. Bulk Payslip Export
- Payslips page now supports:
  - Individual payslip PDF download
  - Whole-run ZIP export containing all employee payslip PDFs
  - Payroll summary CSV included inside the ZIP

### 4. Employer Contributions
- Payroll items now store employer contribution fields:
  - SSS ER
  - SSS EC
  - PhilHealth ER
  - Pag-IBIG ER
- SSS ER/EC follows the same month-to-date catch-up style as SSS EE.
- PhilHealth ER mirrors the employer half of the declared-monthly computation.
- Pag-IBIG ER uses configurable employer rate and ceiling.
- Accounting export queue now creates employer contribution entries:
  - Dr Employer Contributions Expense / Cr SSS Payable
  - Dr Employer Contributions Expense / Cr PhilHealth Payable
  - Dr Employer Contributions Expense / Cr Pag-IBIG Payable

### 5. Annual Review Auto Summary
- Annual review page now generates an auto-summary from:
  - Schedules
  - Time logs
  - Late minutes
  - Undertime minutes
  - Missing/absent days
  - Approved OT
  - Leave usage
  - Infractions
  - Memos
  - Payroll history
- The auto-summary suggests starting scores, but manager/supervisor still controls the final review.

## Still future work
- Final biometric device parser after the actual facial/fingerprint device is purchased.
- True login and role permissions.
- Full drawer reconciliation integration.
- POS/Operations reference data for OT context.
- Final official statutory table review before live payroll use.
- Production rebuild in FastAPI + PostgreSQL + Next.js when ready.
