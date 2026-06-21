import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function headers(json = false): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

export async function GET() {
  const response = await fetch(`${apiBaseUrl()}/api/v1/cash-advances`, {
    headers: await headers(),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const correctionId = Number(body.cash_advance_id || 0);
  const isCorrection = body.action === "correct_amount" && correctionId > 0;
  const endpoint = isCorrection
    ? `${apiBaseUrl()}/api/v1/cash-advances/${correctionId}/correct-amount`
    : `${apiBaseUrl()}/api/v1/cash-advances`;
  const payload = isCorrection
    ? {
        corrected_amount: body.corrected_amount,
        correction_reason: body.correction_reason,
        reference: body.reference || null,
      }
    : body;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: await headers(true),
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/cash-advances");
  return NextResponse.json(data, { status: response.status });
}
