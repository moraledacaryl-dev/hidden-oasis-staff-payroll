import Link from "next/link";
import { redirect } from "next/navigation";
import { HolidayManager, type Holiday } from "@/components/HolidayManager";
import { Shell } from "@/components/Shell";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import { currentSession } from "@/lib/session";

async function getHolidays(): Promise<Holiday[]> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/holidays`, { headers: await backendHeaders(false, true), cache: "no-store" });
  if (!response.ok) throw new Error(`Holiday API failed: ${response.status}`);
  const data = await response.json();
  return data.items || [];
}

export default async function HolidaysPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.role_key !== "owner" && session.role_key !== "payroll") return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  const holidays = await getHolidays();
  return <Shell allowedRoles={["owner", "payroll"]}><div className="page"><header className="page-header"><div className="grid"><span className="eyebrow">Payroll setup</span><h1>Holiday calendar</h1><p className="muted">Configure date-specific Regular Holidays and Special Non-Working Days before payroll is calculated.</p><div className="action-row"><Link className="button ghost" href="/payroll">Payroll preview</Link><Link className="button ghost" href="/payroll/runs">Payroll runs</Link></div></div></header><HolidayManager holidays={holidays} /></div></Shell>;
}
