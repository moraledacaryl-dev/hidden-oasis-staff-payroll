import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const month = new URL(request.url).searchParams.get("month") || "";
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) {
    return NextResponse.json({detail:"Invalid contribution month."},{status:422});
  }
  const response = await fetch(apiBaseUrl()+"/api/v1/payroll/benefits/remittances?month="+encodeURIComponent(month),{
    headers: await backendHeaders(true), cache:"no-store"
  });
  const data = await response.json().catch(()=>({}));
  return NextResponse.json(data,{status:response.status});
}
