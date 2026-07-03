"use client";

import { PayrollAdjustmentEditor } from "@/components/PayrollAdjustmentEditor";

function peso(value?: number | null): string {
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(Number(value || 0));
}

function numberText(value?: number | null): string {
  return Number(value || 0).toLocaleString("en-PH", { maximumFractionDigits: 2 });
}

type PayrollItem = {
  id: number;
  employee_id: number;
  employee_name: string;
  employee_code?: string | null;
  department?: string | null;
  position?: string | null;
  regular_hours?: number;
  approved_ot_hours?: number;
  night_diff_hours?: number;
  regular_pay?: number;
  ot_pay?: number;
  night_diff_pay?: number;
  holiday_pay?: number;
  paid_leave_pay?: number;
  freelance_pay?: number;
  other_earnings?: number;
  gross_pay?: number;
  sss_ee?: number;
  philhealth_ee?: number;
  pagibig_ee?: number;
  tax?: number;
  cash_advance_deduction?: number;
  other_deductions?: number;
  total_deductions?: number;
  net_pay?: number;
  warnings?: string | null;
};

export function EmployeePayrollCard({
  runId,
  item,
  editable,
  open,
  onOpenChange,
}: {
  runId: number;
  item: PayrollItem;
  editable: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const government = Number(item.sss_ee || 0) + Number(item.philhealth_ee || 0) + Number(item.pagibig_ee || 0) + Number(item.tax || 0);
  const warnings = String(item.warnings || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const initials = String(item.employee_name || "E").split(/\s+/).slice(0, 2).map((part) => part.charAt(0)).join("").toUpperCase();

  return (
    <article className="employee-payroll-card">
      <div className="employee-payroll-summary">
        <button className="employee-payroll-toggle" type="button" onClick={() => onOpenChange(!open)} aria-expanded={open}>
          <span className="employee-payroll-avatar">{initials}</span>
          <span className="employee-payroll-person">
            <strong>{item.employee_name}</strong>
            <small>{item.employee_code || "No code"} · {item.department || "Unassigned"}</small>
          </span>
          <span className="employee-payroll-metric"><small>Gross</small><strong>{peso(item.gross_pay)}</strong></span>
          <span className="employee-payroll-metric"><small>Deductions</small><strong>{peso(item.total_deductions)}</strong></span>
          <span className="employee-payroll-net"><small>Net pay</small><strong>{peso(item.net_pay)}</strong></span>
          <span className="employee-payroll-chevron">{open ? "−" : "+"}</span>
        </button>
      </div>

      {open ? (
        <div className="employee-payroll-body">
          <div className="employee-payroll-columns">
            <section>
              <h3>Calculated earnings</h3>
              <p><span>Regular pay <small>{numberText(item.regular_hours)} hrs</small></span><strong>{peso(item.regular_pay)}</strong></p>
              <p><span>Overtime <small>{numberText(item.approved_ot_hours)} hrs</small></span><strong>{peso(item.ot_pay)}</strong></p>
              <p><span>Night differential <small>{numberText(item.night_diff_hours)} hrs</small></span><strong>{peso(item.night_diff_pay)}</strong></p>
              <p><span>Holiday pay</span><strong>{peso(item.holiday_pay)}</strong></p>
              <p><span>Paid leave</span><strong>{peso(item.paid_leave_pay)}</strong></p>
              <p><span>Other earnings</span><strong>{peso(item.other_earnings)}</strong></p>
              <p className="employee-payroll-total"><span>Gross pay</span><strong>{peso(item.gross_pay)}</strong></p>
            </section>

            <section>
              <h3>Deductions</h3>
              <p><span>SSS</span><strong>{peso(item.sss_ee)}</strong></p>
              <p><span>PhilHealth</span><strong>{peso(item.philhealth_ee)}</strong></p>
              <p><span>Pag-IBIG</span><strong>{peso(item.pagibig_ee)}</strong></p>
              <p><span>Tax</span><strong>{peso(item.tax)}</strong></p>
              <p><span>Cash advance repayment</span><strong>{peso(item.cash_advance_deduction)}</strong></p>
              <p><span>Other deductions</span><strong>{peso(item.other_deductions)}</strong></p>
              <p className="employee-payroll-total"><span>Total deductions</span><strong>{peso(item.total_deductions)}</strong></p>
            </section>

            <section className="employee-payslip-preview">
              <h3>Final payslip preview</h3>
              <div><span>Gross pay</span><strong>{peso(item.gross_pay)}</strong></div>
              <div><span>Government and tax</span><strong>− {peso(government)}</strong></div>
              <div><span>Cash advance</span><strong>− {peso(item.cash_advance_deduction)}</strong></div>
              <div><span>Other deductions</span><strong>− {peso(item.other_deductions)}</strong></div>
              <div className="employee-payslip-net"><span>Net pay</span><strong>{peso(item.net_pay)}</strong></div>
            </section>
          </div>

          {warnings.length ? (
            <div className="employee-payroll-warnings">
              <strong>Review required</strong>
              {warnings.map((warning, index) => <p key={`${item.id}-warning-${index}`}>{warning}</p>)}
            </div>
          ) : null}

          <div className="employee-payroll-adjustments">
            <div><h3>Final adjustments</h3><p className="muted">Adjustments apply only to {item.employee_name}. The payslip preview updates after saving.</p></div>
            <PayrollAdjustmentEditor runId={runId} employeeId={item.employee_id} employeeName={item.employee_name} disabled={!editable} />
          </div>
        </div>
      ) : null}
    </article>
  );
}
