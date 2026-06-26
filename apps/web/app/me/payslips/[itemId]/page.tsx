import { notFound, redirect } from "next/navigation";
import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { currentSession } from "@/lib/session";
import { apiBaseUrl, backendHeaders, numberText, peso } from "@/lib/api";

type Item={id:number;period_start:string;period_end:string;payout_date:string;status:string;regular_hours?:number|null;approved_ot_hours?:number|null;night_diff_hours?:number|null;gross_pay:number;total_deductions:number;net_pay:number};
type Result={employee:{name:string;department:string}|null;items:Item[]};

async function load():Promise<Result|null>{
  const headers=await backendHeaders();
  if(!headers.Authorization)return null;
  const response=await fetch(`${apiBaseUrl()}/api/v1/me/payroll`,{headers,cache:"no-store"});
  if(!response.ok)return null;
  return response.json();
}

export default async function Page({params}:{params:Promise<{itemId:string}>}){
  const session=await currentSession();
  if(!session)redirect("/login");
  if(session.role_key!=="staff")return <Shell allowedRoles={["staff"]}><div/></Shell>;
  const [{itemId},data]=await Promise.all([params,load()]);
  const item=data?.items.find(row=>row.id===Number(itemId));
  if(!item||!data?.employee)notFound();
  return <Shell allowedRoles={["staff"]}><div className="page">
    <header className="page-header"><div><span className="eyebrow">My Payslip</span><h1>{data.employee.name}</h1><p className="muted">{item.period_start} to {item.period_end}</p></div><div className="print-actions"><PrintButton label="Print / Save PDF"/></div></header>
    <section className="card staff-payslip-print"><p><strong>Department:</strong> {data.employee.department}</p><p><strong>Payout date:</strong> {item.payout_date}</p><p><strong>Status:</strong> {item.status}</p><div className="grid cols-3"><div><span>Regular hours</span><strong>{numberText(item.regular_hours)}</strong></div><div><span>OT hours</span><strong>{numberText(item.approved_ot_hours)}</strong></div><div><span>Night diff hours</span><strong>{numberText(item.night_diff_hours)}</strong></div></div><div className="grid cols-3"><div><span>Gross pay</span><strong>{peso(item.gross_pay)}</strong></div><div><span>Deductions</span><strong>{peso(item.total_deductions)}</strong></div><div><span>Net pay</span><strong>{peso(item.net_pay)}</strong></div></div></section>
  </div></Shell>;
}
