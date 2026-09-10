import Link from "next/link";
import { PayslipCopy, type PayslipItem, type PayslipRun } from "@/components/EmployeePayslip";
import "@/app/payroll/runs/[id]/payslips/print.css";
import { notFound, redirect } from "next/navigation";
import { PrintButton } from "@/components/PrintButton";
import { Shell } from "@/components/Shell";
import { currentSession } from "@/lib/session";
import { apiBaseUrl, backendHeaders } from "@/lib/api";

type Item = Omit<PayslipItem, "employee_name" | "department"> & Omit<PayslipRun, "id"> & { id: number; payroll_run_id: number; status: string };
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
  return <Shell allowedRoles={["staff"]}><div className="page payslip-page">
    <header className="page-header"><div><span className="eyebrow">My Payslip</span><h1>{data.employee.name}</h1><p className="muted">{item.period_start} to {item.period_end}</p></div><div className="print-actions"><Link className="button secondary" href="/me#my-payslips">Back to my payslips</Link><PrintButton label="Print / Save PDF"/></div></header>
    <article className="payslip-sheet staff-payslip-print"><PayslipCopy item={{ ...item, employee_name: data.employee.name, department: data.employee.department }} run={{ ...item, id: item.payroll_run_id }} copyLabel="Employee Copy" /></article>
  </div></Shell>;
}
