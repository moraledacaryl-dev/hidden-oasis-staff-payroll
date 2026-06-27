import { NextResponse } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";

export async function GET() {
  const response = await fetch(`${apiBaseUrl()}/api/v1/production/backups`, {
    headers: await backendHeaders(false),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}

export async function POST() {
  const response = await fetch(`${apiBaseUrl()}/api/v1/production/backups`, {
    method: "POST",
    headers: await backendHeaders(false),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
