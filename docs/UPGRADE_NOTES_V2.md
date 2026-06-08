# Hidden Oasis Staff & Payroll Prototype — V2 Upgrade Notes

## What was upgraded from the initial zip

1. **Payroll draft protection**
   - Draft payroll can no longer silently replace an Approved, Paid, or Locked run.
   - Paid/locked payroll must be reopened with a reason before recomputation.

2. **Cash advance repayment lifecycle**
   - Payroll now applies cash advance repayments when a payroll run is marked Paid.
   - Repayments are written to `cash_advance_repayments`.
   - Cash advance balances and statuses are updated automatically.
   - Reopening a Paid/Locked payroll reverses the payroll-linked repayment and restores the cash advance balance.

3. **Accounting export queue**
   - Marking payroll as Paid now creates accounting-ready entries for:
     - gross payroll expense
     - SSS payable
     - PhilHealth payable
     - Pag-IBIG payable
     - cash advance receivable reduction
     - net pay release
   - Entries stay in `For Review` status for accounting approval.

4. **Holiday/rest-day premium support**
   - Added holiday calendar table.
   - Added configurable rate multipliers for:
     - regular holiday
     - special holiday
     - rest day
     - regular holiday + rest day
     - special holiday + rest day
     - premium day overtime
   - Payroll now separates ordinary base pay and holiday/rest premium.

5. **Manual payroll adjustments**
   - Added approved manual earnings/deductions per employee and period.
   - These are included in payroll as `other_earnings` or `other_deductions`.

6. **Leave validation warnings**
   - Paid leave now warns when an employee has no entitlement enabled.
   - Paid leave also warns when usage exceeds configured credits.

7. **Payroll preview visibility**
   - Payroll preview now shows holiday/rest premium, other earnings, and other deductions.

8. **Settings expansion**
   - Added holiday calendar UI.
   - Added configurable premium multipliers and payroll cash account setting.

## What is still intentionally incomplete

1. **Exact biometric device parser**
   - Keep flexible import for now. Final parser depends on the device export format.

2. **Full PH holiday edge cases**
   - Current V2 supports a practical multiplier matrix, but still needs final legal/accountant validation for rare combinations.

3. **Employer contribution accounting**
   - Current accounting queue records employee deductions and payroll release. Employer-side SSS/PhilHealth/Pag-IBIG expense/payables should be added after final contribution tables are locked.

4. **Payslip PDF generation**
   - Data lines are now better structured, but PDF payslips are not generated yet.

5. **Role permissions/login**
   - Streamlit prototype has no true login/permissions. Production version should use roles: staff, supervisor, manager, owner/admin.

6. **Drawer reconciliation integration**
   - Cash advance records support drawer reference, but no full cashier drawer module is included in this payroll-only prototype.

7. **Operations/POS context for OT**
   - OT reasons exist, but sales/guest count/occupancy references are not yet automatically pulled from POS/PMS/Operations.

8. **Production UI**
   - This remains a working local prototype. A final SaaS-grade UI should be rebuilt in the main FastAPI + Next.js stack.
