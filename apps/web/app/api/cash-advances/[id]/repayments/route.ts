import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const response = await fetch(`${apiBaseUrl()}/api/v1/cash-advances/${id}/manual-repayments`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify(await request.json()),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/cash-advances");
  return NextResponse.json(data, { status: response.status });
}
