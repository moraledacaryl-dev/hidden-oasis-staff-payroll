import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function POST(request: Request) {
  const body = await request.json();
  const runId = Number(body.run_id);
  if (!runId) return NextResponse.json({ ok: false, message: "Missing payroll run." }, { status: 422 });

  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${runId}/corrections`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({
      employee_id: Number(body.employee_id),
      adjustment_type: body.adjustment_type,
      amount: Number(body.amount || 0),
      reason: body.reason,
      apply_to_next_run: Boolean(body.apply_to_next_run),
    }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    revalidatePath(`/payroll/runs/${runId}/corrections`);
    revalidatePath(`/payroll/runs/${runId}/audit`);
  }
  return NextResponse.json(data, { status: response.status });
}
