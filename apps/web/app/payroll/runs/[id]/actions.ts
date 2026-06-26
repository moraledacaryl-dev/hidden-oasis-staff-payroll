"use server";

import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { revalidatePath } from "next/cache";

async function changePayrollStatus(runId: number, endpoint: "lock" | "approve") {
  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${runId}/${endpoint}`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({}),
    cache: "no-store",
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = typeof data.detail === "string" ? data.detail : data.message;
    throw new Error(detail || "Payroll status was not changed.");
  }

  revalidatePath(`/payroll/runs/${runId}`);
  revalidatePath("/payroll/runs");
  revalidatePath(`/payroll/runs/${runId}/payslips`);
  revalidatePath(`/payroll/runs/${runId}/audit`);
}

export async function submitPayrollForOwnerReview(runId: number) {
  await changePayrollStatus(runId, "lock");
}

export async function approvePayroll(runId: number) {
  await changePayrollStatus(runId, "approve");
}
