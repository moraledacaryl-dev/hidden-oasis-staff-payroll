import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
export async function POST(request:Request){const response=await fetch(`${apiBaseUrl()}/api/v1/payroll/benefits/outside-payment`,{method:"POST",headers:await backendHeaders(true),body:JSON.stringify(await request.json()),cache:"no-store"});const data=await response.json().catch(()=>({}));if(response.ok)revalidatePath("/payroll/benefits");return NextResponse.json(data,{status:response.status});}
