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
  const cashAdvanceId = Number(body.cash_advance_id || body.id || 0);
  const action = String(body.action || "");
  const transitionActions = new Set(["approve", "reject", "cancel"]);
  const isCorrection = action === "correct_amount" && cashAdvanceId > 0;
  const isTransition = transitionActions.has(action) && cashAdvanceId > 0;
  const isSettlement = action === "settle_credit" && cashAdvanceId > 0;

  const endpoint = isCorrection
    ? `${apiBaseUrl()}/api/v1/cash-advances/${cashAdvanceId}/correct-amount`
    : isTransition
      ? `${apiBaseUrl()}/api/v1/cash-advances/${cashAdvanceId}/${action}`
      : isSettlement
        ? `${apiBaseUrl()}/api/v1/cash-advances/${cashAdvanceId}/settle-credit`
        : `${apiBaseUrl()}/api/v1/cash-advances`;

  const payload = isCorrection
    ? {
        corrected_amount: body.corrected_amount,
        correction_reason: body.correction_reason,
        reference: body.reference || null,
      }
    : isTransition
      ? action === "approve" ? {} : { reason: body.reason || null }
      : isSettlement
        ? {
            amount: body.amount,
            method: body.method,
            note: body.note,
            reference: body.reference || null,
            target_cash_advance_id: body.target_cash_advance_id || null,
          }
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
