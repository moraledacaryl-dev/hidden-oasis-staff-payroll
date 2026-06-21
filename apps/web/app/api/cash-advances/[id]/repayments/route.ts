import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

function apiBaseUrl(): string {
  return (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
}

async function authHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const response = await fetch(`${apiBaseUrl()}/api/v1/cash-advances/${id}/manual-repayments`, {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify(await request.json()),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/cash-advances");
  return NextResponse.json(data, { status: response.status });
}
