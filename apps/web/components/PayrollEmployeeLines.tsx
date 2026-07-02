"use client";

import { useState } from "react";
import { numberText, peso, type PayrollReviewItem } from "@/lib/api";

type PayrollPreviewItem = PayrollReviewItem & {
  employee_id: number;
  full_name?: string;
  employee_code?: string | null;
  warnings?: string[] | string | null;
};

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
        return (
          <article className="payroll-employee-card" key={item.employee_id}>
            <button className="payroll-employee-summary" type="button" onClick={() => setOpenId(isOpen ? null : item.employee_id)} aria-expanded={isOpen}>
              <span className="payroll-employee-main"><strong>{employeeName(item)}</strong><small>{item.employee_code || item.department || "No code"}</small></span>
              <span><small>Gross</small><strong>{peso(item.gross_pay)}</strong></span>
              <span><small>Deductions</small><strong>{peso(item.total_deductions)}</strong></span>
              <span className={caDeduction > 0 ? "payroll-ca has-ca" : "payroll-ca"}><small>CA</small><strong>{caDeduction > 0 ? peso(caDeduction) : "—"}</strong></span>
              <span><small>Net</small><strong>{peso(item.net_pay)}</strong></span>
              <span className="payroll-expand-mark">{isOpen ? "−" : "+"}</span>
            </button>

            {isOpen ? (
              <div className="payroll-employee-detail">
                <div className="payroll-detail-grid">
                  <div><span>Regular hours</span><strong>{numberText(item.regular_hours)}</strong></div>
                  <div><span>Regular pay</span><strong>{peso(item.regular_pay)}</strong></div>
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

      <style jsx>{`
        .payroll-employee-list{display:grid;gap:10px}
        .payroll-employee-card{border:1px solid var(--line);border-radius:10px;background:var(--surface);overflow:hidden}
        .payroll-employee-summary{width:100%;display:grid;grid-template-columns:minmax(180px,1.8fr) repeat(4,minmax(90px,.8fr)) 32px;gap:12px;align-items:center;padding:12px 14px;border:0;background:transparent;color:inherit;text-align:left;cursor:pointer}
        .payroll-employee-summary:hover{background:var(--surface-soft)}
        .payroll-employee-summary span{display:grid;gap:2px;min-width:0}
        .payroll-employee-summary small,.payroll-detail-grid span{color:var(--muted);font-size:.68rem;font-weight:800;text-transform:uppercase;letter-spacing:.04em}
        .payroll-employee-summary strong{font-size:.88rem;overflow-wrap:anywhere}
        .payroll-employee-main strong{font-size:.95rem}.payroll-ca.has-ca strong{color:var(--warning)}
        .payroll-expand-mark{place-items:center;width:28px;height:28px;border:1px solid var(--line);border-radius:999px;background:var(--surface-soft);font-size:1.05rem;font-weight:900;color:var(--muted)}
        .payroll-employee-detail{display:grid;gap:14px;padding:14px;border-top:1px solid var(--line);background:var(--surface-soft)}
        .payroll-detail-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
        .payroll-detail-grid div{display:grid;gap:4px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--surface)}
        .payroll-detail-grid strong{font-size:.9rem}.payroll-warning-list{display:grid;gap:6px;padding:12px;border-left:3px solid var(--warning);border-radius:0 8px 8px 0;background:var(--warning-soft)}
        .payroll-warning-list p{margin:0;color:var(--text);font-size:.8rem;line-height:1.35}
        @media(max-width:900px){.payroll-employee-summary{grid-template-columns:1fr 1fr 1fr 32px}.payroll-employee-summary span:nth-of-type(4),.payroll-employee-summary span:nth-of-type(5){grid-column:auto}.payroll-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:640px){.payroll-employee-summary{grid-template-columns:1fr 32px}.payroll-employee-summary>span:not(.payroll-employee-main):not(.payroll-expand-mark){grid-template-columns:1fr 1fr;align-items:center}.payroll-detail-grid{grid-template-columns:1fr}}
      `}</style>
    </div>
  );
}
