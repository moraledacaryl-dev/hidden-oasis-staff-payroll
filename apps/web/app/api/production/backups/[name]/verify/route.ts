import { NextRequest, NextResponse } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";

type Params = { params: Promise<{ name: string }> };

export async function POST(_request: NextRequest, { params }: Params) {
  const { name } = await params;
  const response = await fetch(`${apiBaseUrl()}/api/v1/production/backups/${encodeURIComponent(name)}/verify`, {
    method: "POST",
    headers: await backendHeaders(false),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
