import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const runId = Number(id);
  if (!runId) return NextResponse.json({ ok: false, message: "Missing payroll run." }, { status: 422 });
  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${runId}/undo-schedule-changes`, {
    method: "POST",
    headers: await backendHeaders(),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    revalidatePath(`/payroll/runs/${runId}`);
    revalidatePath("/schedule");
  }
  return NextResponse.json(data, { status: response.status });
}
