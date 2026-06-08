# V5 Upgrade Notes

V5 pushes the local Staff & Payroll prototype closer to a payroll-safe control system while still keeping the original uploaded payroll logic direction.

## Added in V5

### 1. Payroll QA / Preflight Checks
A new Payroll QA page checks the cutoff before payroll approval. It flags:
- pending/disputed attendance logs
- pending OT
- pending leave requests
- scheduled days with no log and no approved leave
- missing time-outs
- employees with no hourly rate
- benefit-enabled employees with no declared monthly base
- cash advances approved but not released
- duplicate reviewed/approved/paid/locked runs for the same cutoff
- leave balances over credits
- missing/outdated-looking SSS table coverage

The payroll draft now saves a `validation_summary` snapshot.

### 2. Role-aware prototype access layer
Added a simple Access Control page and sidebar acting user selector.

Roles are now scaffolded as:
- Owner
- Manager
- Supervisor
- Reception
- Payroll Clerk
- Viewer

This is not real password security yet. The final FastAPI/Next.js version should enforce permissions server-side.

### 3. Cash advance drawer linkage
Cash advances released via Cash Drawer now create a linked drawer cash-out movement:

Cash Advance record → Cash Drawer Movement → Payroll repayment → Accounting queue

This prevents the cash advance from being double-counted as both a drawer expense and a payroll deduction.

### 4. OT operational reference fields
Attendance review can now store OT/context references:
- occupancy / rooms
- guest count
- POS order count
- sales reference
- event/function flag

These are placeholders until the POS/Operations apps feed this data automatically.

### 5. 13th month accounting queue
Paid/locked 13th-month runs now create an accounting export queue entry.

### 6. Better leave cutoff handling
Paid leave that overlaps a payroll period is now prorated to the portion inside the cutoff instead of always applying the entire request days to the current payroll.

### 7. Better template/snapshot coverage
Required template and database snapshot now include:
- AppUsers
- DrawerMovements
- cash_drawer_movements table
- role scaffolding data

## Still missing for 10/10 production use

1. True login, hashed passwords, and backend-enforced permissions.
2. Final biometric device-specific parser after the facial/fingerprint device is purchased.
3. Full POS/Operations integration for occupancy, sales, guest count, order count, and events.
4. Full drawer reconciliation module in the POS/Accounting app.
5. Final review and import of the exact official SSS table before live use.
6. Production Next.js/FastAPI/PostgreSQL implementation.
7. Real accountant-reviewed tax/withholding configuration.
8. Automated leave accrual rules if you want accrual instead of manually configured credits.
