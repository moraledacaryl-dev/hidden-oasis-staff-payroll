import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getMonthlyBenefits, peso } from "@/lib/api";
import { currentSession } from "@/lib/session";

function currentMonth() { return new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Manila",year:"numeric",month:"2-digit"}).format(new Date()); }

export default async function BenefitsPage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  const allowed = ["owner","payroll","supervisor"];
  if (!allowed.includes(session.role_key)) return <Shell allowedRoles={allowed}><div /></Shell>;
  const query = await searchParams;
  const month = /^\d{4}-\d{2}$/.test(query.month || "") ? query.month! : currentMonth();
  const ledger = await getMonthlyBenefits(month);
  return <Shell allowedRoles={allowed}><div className="page run-page">
    <header className="payroll-hero"><div><span className="eyebrow">Statutory benefits</span><h1>Monthly benefits ledger</h1><p className="muted">Read-only monthly SSS, PhilHealth, and Pag-IBIG coverage from authoritative payroll snapshots.</p></div><div className="payroll-actions"><Link className="button secondary" href="/payroll/runs">Payroll runs</Link></div></header>
    <section className="payroll-toolbar"><form><label>Calendar month<input name="month" type="month" defaultValue={month}/></label><button className="button" type="submit">View month</button></form><p className="muted">General Managers can review this ledger. Payroll corrections remain controlled by the payroll workflow.</p></section>
    <section className="run-list"><header><div><h2>{month} contributions</h2><p>{ledger.items.length} employee records. Pending rows show the first date not yet represented by a settled payroll snapshot.</p></div><StatusBadge label={ledger.items.some(x=>x.status!=="Complete") ? "Pending coverage" : "Complete"} tone={ledger.items.some(x=>x.status!=="Complete") ? "warning" : "ok"} /></header>
    <div className="table-wrap"><table className="run-table"><thead><tr><th>Employee</th><th>Coverage</th><th>SSS</th><th>PhilHealth</th><th>Pag-IBIG</th><th>Gross basis</th><th>Source runs</th></tr></thead><tbody>
    {ledger.items.map(item=><tr key={item.employee_id}><td><strong>{item.full_name}</strong><br/><span className="muted">{item.employee_code || "—"}</span></td><td><StatusBadge label={item.status} tone={item.status==="Complete"?"ok":"warning"}/><br/><span className="muted">{item.status==="Complete" ? `Through ${item.covered_through}` : `Missing from ${item.missing_from}`}</span></td><td><strong>{peso(item.sss_ee)}</strong><br/><span className="muted">ER {peso(item.sss_er)} · EC {peso(item.sss_ec)}</span></td><td><strong>{peso(item.philhealth_ee)}</strong><br/><span className="muted">ER {peso(item.philhealth_er)}</span></td><td><strong>{peso(item.pagibig_ee)}</strong><br/><span className="muted">ER {peso(item.pagibig_er)}</span></td><td>{peso(item.gross_pay)}</td><td>{item.runs.map(r=><div key={r.run_id}><Link href={session.role_key==="supervisor" ? "/payroll/benefits" : `/payroll/runs/${r.run_id}`}>#{r.run_id}</Link> <span className="muted">{r.period_start}–{r.period_end}</span></div>)}</td></tr>)}
    {ledger.items.length===0?<tr><td colSpan={7}>{ledger.message || "No settled statutory snapshots for this month yet."}</td></tr>:null}
    </tbody></table></div></section>
  </div></Shell>;
}
