"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./BenefitForms.module.css";

export function AgencyRemittanceForm({month}:{month:string}) {
  const router=useRouter();
  const [program,setProgram]=useState("sss");
  const [amount,setAmount]=useState("");
  const [paymentDate,setPaymentDate]=useState("");
  const [reference,setReference]=useState("");
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  async function submit(event:React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);setMessage("");
    try {
      const response=await fetch("/api/payroll/benefits/remittances",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({program,contribution_month:month,payment_date:paymentDate,amount:Number(amount),reference})});
      const result=await response.json().catch(()=>({}));
      if(!response.ok) {setMessage(String(result.detail||"Unable to record remittance."));return;}
      setAmount("");setReference("");setMessage("Remittance recorded.");window.dispatchEvent(new CustomEvent("agency-remittance-saved"));router.refresh();
    } catch {setMessage("Unable to connect to the server.");}
    finally {setBusy(false);}
  }
  return <form onSubmit={submit} className={styles.remittance}>
    <label>Agency<select value={program} onChange={e=>setProgram(e.target.value)}><option value="sss">SSS</option><option value="philhealth">PhilHealth</option><option value="pagibig">Pag-IBIG</option></select></label>
    <label>Payment date<input type="date" required value={paymentDate} onChange={e=>setPaymentDate(e.target.value)}/></label>
    <label>Amount remitted<input type="number" required min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></label>
    <label>Receipt/reference<input value={reference} onChange={e=>setReference(e.target.value)}/></label>
    <button className="button" disabled={busy} type="submit">{busy?"Saving…":"Record remittance"}</button>
    {message?<p className={styles.message} role="status">{message}</p>:null}
  </form>;
}
