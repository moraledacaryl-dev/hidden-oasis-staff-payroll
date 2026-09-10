"use client";

import { useState } from "react";

type PayrollPreviewItem = {
  employee_id: number;
  employee_name?: string;
  full_name?: string;
  employee_code?: string | null;
  department?: string | null;
  regular_hours?: number | null;
  regular_pay?: number | null;
  approved_ot_hours?: number | null;
  ot_pay?: number | null;
  night_diff_pay?: number | null;
  holiday_pay?: number | null;
  paid_leave_pay?: number | null;
  gross_pay?: number | null;
  sss_ee?: number | null;
  philhealth_ee?: number | null;
  pagibig_ee?: number | null;
  tax?: number | null;
  cash_advance_deduction?: number | null;
  other_deductions?: number | null;
  total_deductions?: number | null;
  net_pay?: number | null;
  warnings?: string[] | string | null;
};

function peso(value?: number | null): string {
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP", maximumFractionDigits: 2 }).format(Number(value || 0));
}

function numberText(value?: number | null, digits = 2): string {
  return Number(value || 0).toLocaleString("en-PH", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function warningsFor(item: PayrollPreviewItem): string[] {
  if (Array.isArray(item.warnings)) return item.warnings.filter(Boolean);
  if (typeof item.warnings === "string" && item.warnings.trim()) {
    return item.warnings.split("|").map((text) => text.trim()).filter(Boolean);
  }
  return [];
}

function employeeName(item: PayrollPreviewItem): string {
  return item.full_name || item.employee_name || "Employee";
}

export function PayrollEmployeeLines({ items }: { items: PayrollPreviewItem[] }) {
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <div className="payroll-employee-list">
      {items.map((item) => {
        const warnings = warningsFor(item);
        const isOpen = openId === item.employee_id;
        const caDeduction = Number(item.cash_advance_deduction || 0);
        const holidayPay = Number(item.holiday_pay || 0);
        return (
          <article className="payroll-employee-card" key={item.employee_id}>
            <button className="payroll-employee-summary" type="button" onClick={() => setOpenId(isOpen ? null : item.employee_id)} aria-expanded={isOpen}>
              <span className="payroll-employee-main"><strong>{employeeName(item)}</strong><small>{item.employee_code || item.department || "No code"}</small></span>
              <span className="payroll-gross"><small>Gross</small><strong>{peso(item.gross_pay)}</strong></span>
              <span className={holidayPay > 0 ? "payroll-holiday has-holiday" : "payroll-holiday"}><small>Holiday</small><strong>{holidayPay > 0 ? peso(holidayPay) : "—"}</strong></span>
              <span className="payroll-deductions"><small>Deductions</small><strong>{peso(item.total_deductions)}</strong></span>
              <span className={caDeduction > 0 ? "payroll-ca has-ca" : "payroll-ca"}><small>CA</small><strong>{caDeduction > 0 ? peso(caDeduction) : "—"}</strong></span>
              <span className="payroll-net"><small>Net</small><strong>{peso(item.net_pay)}</strong></span>
              <span className="payroll-expand-mark">{isOpen ? "−" : "+"}</span>
            </button>

            {isOpen ? (
              <div className="payroll-employee-detail">
                <div className="payroll-detail-grid">
                  <div><span>Regular hours</span><strong>{numberText(item.regular_hours)}</strong></div>
                  <div><span>Regular pay</span><strong>{peso(item.regular_pay)}</strong></div>
                  <div><span>Holiday pay</span><strong>{peso(item.holiday_pay)}</strong></div>
                  <div><span>OT hours</span><strong>{numberText(item.approved_ot_hours)}</strong></div>
                  <div><span>OT pay</span><strong>{peso(item.ot_pay)}</strong></div>
                  <div><span>Night diff</span><strong>{peso(item.night_diff_pay)}</strong></div>
                  <div><span>Leave pay</span><strong>{peso(item.paid_leave_pay)}</strong></div>
                  <div><span>SSS</span><strong>{peso(item.sss_ee)}</strong></div>
                  <div><span>PhilHealth</span><strong>{peso(item.philhealth_ee)}</strong></div>
                  <div><span>Pag-IBIG</span><strong>{peso(item.pagibig_ee)}</strong></div>
                  <div><span>Tax</span><strong>{peso(item.tax)}</strong></div>
                  <div><span>Cash advance</span><strong>{peso(item.cash_advance_deduction)}</strong></div>
                  <div><span>Other deductions</span><strong>{peso(item.other_deductions)}</strong></div>
                </div>
                {warnings.length ? (
                  <div className="payroll-warning-list">
                    <strong>Warnings</strong>
                    {warnings.map((warning, index) => <p key={`${item.employee_id}-${index}`}>{warning}</p>)}
                  </div>
                ) : <p className="muted">No warnings for this employee.</p>}
              </div>
            ) : null}
          </article>
        );
      })}
      {!items.length ? <p className="muted">No employee payroll lines found.</p> : null}


    </div>
  );
}
