import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function GET() {
  const response = await fetch(`${apiBaseUrl()}/api/v1/cash-advances`, {
    headers: await backendHeaders(),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const correctionId = Number(body.cash_advance_id || 0);
  const approveId = Number(body.cash_advance_id || body.id || 0);
  const isCorrection = body.action === "correct_amount" && correctionId > 0;
  const isApproval = body.action === "approve" && approveId > 0;
  const endpoint = isCorrection
    ? `${apiBaseUrl()}/api/v1/cash-advances/${correctionId}/correct-amount`
    : isApproval
      ? `${apiBaseUrl()}/api/v1/cash-advances/${approveId}/approve`
      : `${apiBaseUrl()}/api/v1/cash-advances`;
  const payload = isCorrection
    ? {
        corrected_amount: body.corrected_amount,
        correction_reason: body.correction_reason,
        reference: body.reference || null,
      }
    : isApproval
      ? {}
      : body;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/cash-advances");
  return NextResponse.json(data, { status: response.status });
}
