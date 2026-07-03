"use client";

import { useState } from "react";
import { EmployeePayrollCard } from "@/components/EmployeePayrollCard";
import { usePayrollReviewAccordion } from "@/components/PayrollReviewAccordion";
import type { PayrollReviewItem } from "@/lib/api";

export function PayrollEmployeeAccordion({
  runId,
  items,
  editable,
}: {
  runId: number;
  items: PayrollReviewItem[];
  editable: boolean;
}) {
  const localAccordion = useState<string | null>(null);
  const sharedAccordion = usePayrollReviewAccordion();
  const openId = sharedAccordion?.openId ?? localAccordion[0];
  const setOpenId = sharedAccordion?.setOpenId ?? localAccordion[1];

  if (!items.length) {
    return <div className="card"><p>No payroll items found.</p></div>;
  }

  return (
    <>
      {items.map((item) => {
        const employeeId = Number(item.employee_id);
        const employeeOpenId = `employee-${employeeId}`;
        const open = openId === employeeOpenId;
        return (
          <EmployeePayrollCard
            key={item.id}
            runId={runId}
            item={item}
            editable={editable}
            open={open}
            onOpenChange={(nextOpen) => setOpenId(nextOpen ? employeeOpenId : null)}
          />
        );
      })}
    </>
  );
}
