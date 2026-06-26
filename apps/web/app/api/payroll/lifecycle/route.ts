import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function POST(request: Request) {
  const body = await request.json();
  const runId = Number(body.run_id);
  const action = String(body.action || "");
  const reason = String(body.reason || "");
  if (!runId || !["lock", "approve", "reopen"].includes(action)) {
    return NextResponse.json({ ok: false, message: "Invalid payroll action." }, { status: 422 });
  }

  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${runId}/${action}`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: action === "reopen" ? JSON.stringify({ reason }) : undefined,
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    revalidatePath("/cutoff");
    revalidatePath("/payroll/runs");
    revalidatePath(`/payroll/runs/${runId}`);
    revalidatePath(`/payroll/runs/${runId}/audit`);
  }
  return NextResponse.json(data, { status: response.status });
}
