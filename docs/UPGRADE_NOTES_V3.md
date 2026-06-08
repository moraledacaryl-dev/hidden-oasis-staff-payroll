# V3 Upgrade Notes

## Added / Restored

1. **Payslip PDF generation**
   - Added a dedicated Payslips page.
   - Saved payroll runs can now generate a downloadable PDF payslip per employee.
   - Uses payroll item lines so earnings/deductions remain transparent.

2. **13th Month Pay module**
   - Added a dedicated 13th Month Pay page.
   - Computes basis from saved payroll history.
   - Default basis: regular/basic pay + paid leave pay only.
   - Excludes OT, night differential, holiday/rest-day premiums, allowances, reimbursements, and freelance output pay unless manually adjusted.
   - Supports manual adjustment, deductions, status, release date, history, and downloadable 13th month payslip PDF.

3. **Basic biometric importer**
   - Kept intentionally generic until the final device export is known.
   - Supports two modes:
     - Timestamp rows: one punch per row, grouped into earliest IN and latest OUT.
     - Daily rows: one row already has Time In and Time Out columns.
   - Imported logs remain Pending so supervisors still review exceptions and OT.

4. **Company settings for PDF output**
   - Added company name and address settings.
   - Added 13th month basis setting label for documentation.

5. **Database support**
   - Added payroll_13th_month_runs.
   - Added payroll_13th_month_lines.
   - Added biometric_import_profiles as a future-ready placeholder.

## Preserved from V2

- Actual-hours payroll basis.
- Semi-monthly cutoff logic.
- SSS actual month-to-date catch-up method.
- PhilHealth and Pag-IBIG declared monthly split/catch-up basis.
- Supervisor-approved OT only.
- Configurable leaves and leave entitlements.
- Cash advance ledger and payroll repayment.
- Freelance/output-based pay.
- Payroll status workflow and locking.
- Accounting export queue.
- Infractions, memos, requests, and annual reviews.

## Still Missing / Future Work

1. Device-specific biometric parser once the actual facial/fingerprint hardware export is known.
2. Full user login/role permission system.
3. Production-grade FastAPI/PostgreSQL/Next.js version.
4. Full drawer reconciliation integration for cash advance release.
5. Full employer-side contribution accounting.
6. Exact official SSS table import/validation screen.
7. Automatic OT context from POS/PMS/Operations data.
8. More polished annual review dashboard with automatic attendance/performance summary.
