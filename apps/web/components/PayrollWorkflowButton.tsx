"use client";

import { useFormStatus } from "react-dom";
import { approvePayroll, submitPayrollForOwnerReview } from "@/app/payroll/runs/[id]/actions";

type Action = "submit-review" | "approve";

function SubmitButton({ action }: { action: Action }) {
  const { pending } = useFormStatus();
  const isApprove = action === "approve";
  const label = isApprove ? "Approve payroll" : "Submit for owner review";

  return (
    <button className={isApprove ? "primary-button" : "button"} type="submit" disabled={pending}>
      {pending ? "Saving..." : label}
    </button>
  );
}

export function PayrollWorkflowButton({ runId, action }: { runId: number; action: Action }) {
  const formAction = action === "approve"
    ? approvePayroll.bind(null, runId)
    : submitPayrollForOwnerReview.bind(null, runId);

  return (
    <form action={formAction}>
      <SubmitButton action={action} />
    </form>
  );
}
