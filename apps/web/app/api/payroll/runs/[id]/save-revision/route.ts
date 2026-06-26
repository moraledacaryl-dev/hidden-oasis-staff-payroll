import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const runId = Number(id);
  if (!runId) return NextResponse.json({ ok: false, message: "Missing payroll run." }, { status: 422 });
  const body = await request.json().catch(() => ({}));
  const response = await fetch(`${apiBaseUrl()}/api/v1/payroll/runs/${runId}/save-controlled-revision`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({
      run_label: body.run_label || null,
      revision_reason: body.revision_reason || "",
      treatment: body.treatment || null,
    }),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    revalidatePath(`/payroll/runs/${runId}`);
    revalidatePath("/payroll/runs");
  }
  return NextResponse.json(data, { status: response.status });
}
