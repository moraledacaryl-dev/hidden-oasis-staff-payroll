import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const response = await fetch(`${apiBaseUrl()}/api/v1/attendance/compliance?${url.searchParams.toString()}`, {
    headers: await backendHeaders(),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: Request) {
  const body = await request.json();
  const response = await fetch(`${apiBaseUrl()}/api/v1/attendance/memos`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) revalidatePath("/attendance/compliance");
  return NextResponse.json(data, { status: response.status });
}
