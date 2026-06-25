"use client";
import {useEffect,useState} from "react";
import {StaffShiftRequests} from "@/components/StaffShiftRequests";

type LeaveBalance={leave_type_name:string;credits:number;used:number;remaining:number};
type HrRecord={id:number;record_date:string;record_type:string;subject:string;severity:string;status:string;issued_by?:string|null};

export function StaffSelfServicePanel(){
  const [data,setData]=useState<any>(null);
  const [leave,setLeave]=useState<LeaveBalance[]>([]);
  const [records,setRecords]=useState<HrRecord[]>([]);
  const [error,setError]=useState("");
  useEffect(()=>{
    Promise.all([
      fetch("/api/schedule/shifts",{cache:"no-store"}),
      fetch(`/api/hr/leave-balances?year=${new Date().getFullYear()}`,{cache:"no-store"}),
      fetch("/api/hr/records",{cache:"no-store"}),
    ]).then(async([selfRes,leaveRes,recordsRes])=>{
      const selfBody=await selfRes.json().catch(()=>({}));
      if(!selfRes.ok)throw new Error(selfBody.detail||selfBody.message||"Could not load self-service.");
      const leaveBody=await leaveRes.json().catch(()=>({items:[]}));
      const recordsBody=await recordsRes.json().catch(()=>({items:[]}));
      setData(selfBody);
      setLeave(leaveBody.items?.[0]?.balances||[]);
      setRecords(recordsBody.items||[]);
    }).catch(e=>setError(e instanceof Error?e.message:"Could not load self-service."))
  },[]);
  if(error)return <section className="card"><strong>Self-service unavailable</strong><p className="muted">{error}</p></section>;
  if(!data)return <section className="card"><p className="muted">Loading your schedule, requests, and HR information…</p></section>;
  if(!data.employee)return <section className="card"><strong>Employee account not linked</strong><p className="muted">Ask management to link your login to your employee record.</p></section>;
  return <>
    <StaffShiftRequests employeeId={data.employee.id} schedule={data.schedule||[]} requests={data.requests||[]} coworkers={data.coworkers||[]} publications={data.publications||[]}/>
    <section className="grid cols-2">
      <div className="card"><div className="panel-title"><div><h2>My leave balances</h2><p className="muted">Only your own leave information is shown.</p></div></div>{leave.length?leave.map(item=><p key={item.leave_type_name}><strong>{item.leave_type_name}</strong><br/><span className="muted">{Number(item.remaining||0).toLocaleString("en-PH")} remaining of {Number(item.credits||0).toLocaleString("en-PH")}</span></p>):<p className="muted">No leave entitlement records.</p>}</div>
      <div className="card"><div className="panel-title"><div><h2>My HR records</h2><p className="muted">Issued records linked only to your employee profile.</p></div></div>{records.length?records.map(item=><p key={item.id}><strong>{item.record_date} · {item.record_type}</strong><br/>{item.subject}<br/><span className="muted">{item.status} · {item.severity}{item.issued_by?` · ${item.issued_by}`:""}</span></p>):<p className="muted">No released HR records.</p>}</div>
    </section>
  </>;
}
