import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.text();

  const response = await fetch(`${apiBaseUrl()}/api/v1/performance/logs`, {
    method: "POST",
    headers: await backendHeaders(true),
    body,
    cache: "no-store",
  });

  const text = await response.text();

  return new NextResponse(text, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") || "application/json",
    },
  });
}
