"use server";

import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

async function changePayrollStatus(
  runId: number,
  endpoint: "lock" | "approve",
) {
  const response = await fetch(
    `${apiBaseUrl()}/api/v1/payroll/runs/${runId}/${endpoint}`,
    {
      method: "POST",
      headers: await backendHeaders(true),
      body: JSON.stringify({}),
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = (
      typeof data.detail === "string"
        ? data.detail
        : typeof data.message === "string"
          ? data.message
          : "Payroll status was not changed."
    );

    const query = new URLSearchParams({
      workflow_error: detail,
    });

    redirect(`/payroll/runs/${runId}?${query.toString()}`);
  }

  revalidatePath(`/payroll/runs/${runId}`);
  revalidatePath("/payroll/runs");
  revalidatePath(`/payroll/runs/${runId}/payslips`);
  revalidatePath(`/payroll/runs/${runId}/audit`);

  const query = new URLSearchParams({
    workflow_success: (
      endpoint === "approve"
        ? "Payroll approved successfully."
        : "Payroll submitted for owner review."
    ),
  });

  redirect(`/payroll/runs/${runId}?${query.toString()}`);
}

export async function submitPayrollForOwnerReview(runId: number) {
  await changePayrollStatus(runId, "lock");
}

export async function approvePayroll(runId: number) {
  await changePayrollStatus(runId, "approve");
}
