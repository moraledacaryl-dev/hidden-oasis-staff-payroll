"use client";
import {useEffect,useState} from "react";
import {StaffShiftRequests} from "@/components/StaffShiftRequests";

export function StaffSelfServicePanel(){
  const [data,setData]=useState<any>(null);
  const [error,setError]=useState("");
  useEffect(()=>{fetch("/api/schedule/day?self_service=1",{cache:"no-store"}).then(async r=>{const b=await r.json().catch(()=>({}));if(!r.ok)throw new Error(b.detail||b.message||"Could not load self-service.");setData(b)}).catch(e=>setError(e instanceof Error?e.message:"Could not load self-service."))},[]);
  if(error)return <section className="card"><strong>Self-service unavailable</strong><p className="muted">{error}</p></section>;
  if(!data)return <section className="card"><p className="muted">Loading your schedule and requests…</p></section>;
  if(!data.employee)return <section className="card"><strong>Employee account not linked</strong><p className="muted">Ask management to link your login to your employee record.</p></section>;
  return <StaffShiftRequests employeeId={data.employee.id} schedule={data.schedule||[]} requests={data.requests||[]} coworkers={data.coworkers||[]}/>;
}
