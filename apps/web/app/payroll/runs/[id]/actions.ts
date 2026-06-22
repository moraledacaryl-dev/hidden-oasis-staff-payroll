"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function changePayrollStatus(runId: number, endpoint: "lock" | "approve") {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) throw new Error("Not signed in.");

  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${runId}/${endpoint}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    },
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
