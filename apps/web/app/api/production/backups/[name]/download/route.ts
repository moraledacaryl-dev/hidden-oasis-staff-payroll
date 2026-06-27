import { NextRequest } from "next/server";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";

type Params = { params: Promise<{ name: string }> };

export async function GET(_request: NextRequest, { params }: Params) {
  const { name } = await params;
  const response = await fetch(`${apiBaseUrl()}/api/v1/production/backups/${encodeURIComponent(name)}/download`, {
    headers: await backendHeaders(false),
    cache: "no-store",
  });
  const body = await response.arrayBuffer();
  const headers = new Headers();
  const contentType = response.headers.get("content-type") || "application/octet-stream";
  headers.set("content-type", contentType);
  const disposition = response.headers.get("content-disposition");
  if (disposition) headers.set("content-disposition", disposition);
  return new Response(body, { status: response.status, headers });
}
