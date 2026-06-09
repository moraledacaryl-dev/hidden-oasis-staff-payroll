# Staff/Payroll End-to-End Scenario Tests

Date: 2026-06-09

Staff/Payroll is the source of truth for employees, attendance, leaves, cash advances, payroll, payslips, 13th month, infractions, memos, annual reviews, and payroll QA. Receivers only get review/status events.

| Scenario | Expected Result | Actual Result | Status | Notes |
| --- | --- | --- | --- | --- |
| Employee sync | Exports only safe identity fields | Unit test passes safe field allowlist and stable external ID | Pass |
| Attendance exception / OT | Operations receives counts/status only, not payroll details | Operations snapshot payload test passes count-only behavior | Pass for local unit logic |
| Leave request | Operations can see pending leave status without owning leave balance | Payload contract documented | Partial | Needs live sample leave event |
| Cash advance release | Accounting receives receivable/cash preview only | Payload builder exists and contract documented | Partial | Live Accounting POST not executed |
| Cash advance repayment | Accounting receives repayment preview through payroll deduction | Unit test passes enveloped repayment payload | Pass |
| Payroll cutoff | Staff computes payroll; Accounting receives review-only totals/preview | Unit test passes contribution/tax payload checks | Pass for local unit logic |
| 13th month | Accounting receives paid 13th month preview | Payload builder and contract documented | Partial | Live sample run not executed |
| Operations snapshot | Operations receives dashboard counts only | Unit test passes | Pass |
| Direct Accounting POST | Ready Accounting events POST to Accounting review endpoints with API key header | Unit test passes using fake receiver | Pass |
| Direct Operations POST | Ready Operations events POST to Operations review endpoint with API key header | Unit test passes using fake receiver | Pass |
| Destination filtering | Accounting POST does not mark Operations-only events as Error | Regression test passes | Pass |
| Failed receiver retry | Failed POST increments attempts and leaves visible Error status | Covered by direct post failure path; live outage not simulated | Partial |
| Launcher routing | Staff opens at `https://staff.hiddenoasis.app` from static launcher | Deployment files prepared | Partial | Needs live nginx/cert setup |
