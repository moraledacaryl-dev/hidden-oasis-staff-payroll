"use client";
import {useEffect,useState} from "react";


type Payment = {id:number;program:string;payment_date:string;amount:number;reference:string|null;created_by:string;source_type:string};
export function AgencyRemittanceHistory({month}:{month:string}) {
  const [items,setItems]=useState<Payment[]>([]);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{const refresh=()=>setRevision(n=>n+1);window.addEventListener("agency-remittance-saved",refresh);return ()=>window.removeEventListener("agency-remittance-saved",refresh);},[]);
  useEffect(()=>{
    let active=true;
    setLoading(true);setError("");
    fetch("/api/payroll/benefits/remittance-history?month="+encodeURIComponent(month),{cache:"no-store"})
      .then(async r=>{const data=await r.json();if(!r.ok)throw new Error(data.detail||"Unable to load remittances");return data;})
      .then(data=>{if(active){setItems(data.items||[]);setError("");}})
      .catch(e=>{if(active)setError(String(e.message||e));})
      .finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;};
  },[month,revision]);
  if(loading)return <p role="status">Loading agency payments…</p>;
  if(error)return <p role="alert">{error}</p>;
  return <div className="table-wrap"><table className="run-table responsive-records"><thead><tr><th>Agency</th><th>Payment date</th><th>Amount</th><th>Reference</th><th>Recorded by</th></tr></thead><tbody>
    {items.map(x=><tr key={x.id}><td data-label="Agency">{x.program==="sss"?"SSS":x.program==="philhealth"?"PhilHealth":"Pag-IBIG"}</td><td data-label="Payment date">{x.payment_date}</td><td data-label="Amount">{new Intl.NumberFormat("en-PH",{style:"currency",currency:"PHP"}).format(x.amount)}</td><td data-label="Reference">{x.reference||"—"}</td><td data-label="Recorded by">{x.created_by}</td></tr>)}
    {items.length===0?<tr><td colSpan={5}>No government remittances recorded for this month.</td></tr>:null}
  </tbody></table></div>;
}
