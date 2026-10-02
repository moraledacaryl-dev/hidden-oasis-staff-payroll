"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppDrawer } from "@/components/AppSurface";

type Line = { id:number; program:"philhealth"|"pagibig"; contribution_month:string; amount:number; label:string; note?:string|null };
const peso=(v:number)=>new Intl.NumberFormat("en-PH",{style:"currency",currency:"PHP"}).format(Number(v||0));

export function BenefitCatchupEditor({runId,employeeId,employeeName,disabled=false}:{runId:number;employeeId:number;employeeName:string;disabled?:boolean}) {
  const router=useRouter();
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
  const [items,setItems]=useState<Line[]>([]),[program,setProgram]=useState<"philhealth"|"pagibig">("philhealth");
  const [month,setMonth]=useState(""),[amount,setAmount]=useState(0),[note,setNote]=useState("");
  async function load(){const r=await fetch(`/api/payroll/runs/${runId}/employees/${employeeId}/benefit-catchups`,{cache:"no-store"});const d=await r.json().catch(()=>({}));if(r.ok){setItems(d.items||[])}else setMessage(d.detail||"Could not load benefit catch-ups.");}
  useEffect(()=>{if(open) void load();},[open]);
  async function save(){if(!month){setMessage("Choose the contribution month.");return;}setBusy(true);setMessage("");const r=await fetch(`/api/payroll/runs/${runId}/employees/${employeeId}/benefit-catchups`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({program,contribution_month:month,amount,note:note.trim()||null})});const d=await r.json().catch(()=>({}));setBusy(false);if(!r.ok){setMessage(d.detail||"Could not save catch-up.");return;}setItems(d.items||[]);setAmount(0);setNote("");router.refresh();}
  async function remove(line:Line){setProgram(line.program);setMonth(line.contribution_month.slice(0,7));setBusy(true);const r=await fetch(`/api/payroll/runs/${runId}/employees/${employeeId}/benefit-catchups`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({program:line.program,contribution_month:line.contribution_month.slice(0,7),amount:0})});const d=await r.json().catch(()=>({}));setBusy(false);if(r.ok){setItems(d.items||[]);router.refresh();}else setMessage(d.detail||"Could not remove catch-up.");}
  if(disabled)return null;
  return <><button className="button small" type="button" onClick={()=>setOpen(true)}>Benefit catch-up</button><AppDrawer open={open} eyebrow="Statutory benefits" title={employeeName} description="Collect a missed PhilHealth or Pag-IBIG employee contribution in this payroll. The contribution month stays separate from the payout period." onClose={()=>!busy&&setOpen(false)}>
    <div style={{display:"grid",gap:14}}>
      {items.length?<div><strong>Catch-ups in this payroll</strong>{items.map(line=><div key={line.id} style={{display:"flex",justifyContent:"space-between",gap:12,marginTop:8}}><span>{line.label}</span><span><strong>{peso(line.amount)}</strong> <button className="button small" type="button" disabled={busy} onClick={()=>void remove(line)}>Remove</button></span></div>)}</div>:<p className="muted">No benefit catch-ups added yet.</p>}
      <label>Benefit<select value={program} onChange={e=>setProgram(e.target.value as "philhealth"|"pagibig")}><option value="philhealth">PhilHealth</option><option value="pagibig">Pag-IBIG</option></select></label>
      <label>Contribution month<input type="month" value={month} onChange={e=>setMonth(e.target.value)}/></label>
      <label>Amount to deduct<input type="number" min="0" step="0.01" value={amount} onChange={e=>setAmount(Number(e.target.value||0))}/></label>
      <label>Note (optional)<input value={note} onChange={e=>setNote(e.target.value)} placeholder="e.g. Missed due to cutoff change"/></label>
      <p className="muted">The payslip will label this separately, for example “PhilHealth — 2026-09 catch-up”. If that month is already fully settled, the save is blocked.</p>
      {message?<p style={{color:"var(--danger, #a33)"}}>{message}</p>:null}
      <div style={{display:"flex",justifyContent:"flex-end",gap:8}}><button className="button ghost" type="button" onClick={()=>setOpen(false)} disabled={busy}>Close</button><button className="primary-button" type="button" onClick={()=>void save()} disabled={busy||amount<=0}>{busy?"Saving…":"Add catch-up"}</button></div>
    </div>
  </AppDrawer></>;
}
