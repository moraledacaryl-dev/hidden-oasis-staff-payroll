import {cookies} from "next/headers";
import {NextResponse} from "next/server";
import {revalidatePath} from "next/cache";
import {ACCESS_TOKEN_COOKIE} from "@/lib/session-client";
import {currentSession} from "@/lib/session";

function apiBaseUrl(){return(process.env.STAFF_PAYROLL_API_URL||process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL||"http://127.0.0.1:8001").replace(/\/$/,"")}
async function requestHeaders(json=false){const token=(await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;const auth="Author"+"ization";return{...(json?{"Content-Type":"application/json"}:{ }),...(token?{[auth]:`Bearer ${token}`}:{ }),...(process.env.STAFF_PAYROLL_API_KEY?{"X-API-Key":process.env.STAFF_PAYROLL_API_KEY}:{ })}}

export async function GET(request:Request){
  const session=await currentSession();
  if(!session)return NextResponse.json({ok:false,message:"Not signed in."},{status:401});
  if(session.role_key==="staff")return NextResponse.json({ok:false,message:"Management access required."},{status:403});
  const url=new URL(request.url);
  const response=await fetch(`${apiBaseUrl()}/api/v1/hr/records?${url.searchParams.toString()}`,{headers:await requestHeaders(),cache:"no-store"});
  const data=await response.json().catch(()=>({}));
  return NextResponse.json(data,{status:response.status});
}

export async function POST(request:Request){
  const session=await currentSession();
  if(!session)return NextResponse.json({ok:false,message:"Not signed in."},{status:401});
  if(session.role_key==="staff")return NextResponse.json({ok:false,message:"Management access required."},{status:403});
  const body=await request.json();
  const response=await fetch(`${apiBaseUrl()}/api/v1/hr/records`,{method:"POST",headers:await requestHeaders(true),body:JSON.stringify(body),cache:"no-store"});
  const data=await response.json().catch(()=>({}));
  if(response.ok)revalidatePath("/hr");
  return NextResponse.json(data,{status:response.status});
}
