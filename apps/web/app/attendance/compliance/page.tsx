import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl } from "@/lib/api";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";
import { cookies } from "next/headers";

function defaultMonth() {
  return new Date().toISOString().slice(0, 7);
}

async function headers(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    Accept: "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

async function loadData(month: string) {
  const response = await fetch(`${apiBaseUrl()}/api/v1/attendance/compliance?month=${month}`, {
    headers: await headers(),
    cache: "no-store",
  });
  if (!response.ok) return { ok: false, items: [], memos: [] };
  return response.json();
}

function numberText(value: unknown) {
  return Number(value || 0).toLocaleString("en-PH");
}

export default async function AttendanceCompliancePage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;
  const params = await searchParams;
  const month = params.month || defaultMonth();
  const data = await loadData(month);
  const items = data.items || [];
  const actionCount = items.filter((item: any) => item.handbook_action !== "No handbook action required").length;

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Attendance Compliance</span><h1>{month}</h1><p className="muted">Monthly attendance infraction summary.</p></div>
          <StatusBadge label={actionCount ? `${actionCount} action needed` : "clear"} tone={actionCount ? "warning" : "ok"} />
        </header>
        <section className="card"><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Missing</th><th>Lates</th><th>Partial</th><th>Unexcused</th><th>AWOL</th><th>Action</th></tr></thead><tbody>{items.map((item: any) => <tr key={item.employee_id}><td><strong>{item.full_name}</strong><br /><span className="muted">{item.department || "—"}</span></td><td>{numberText(item.missing_logs)}</td><td>{numberText(item.late_infractions)}</td><td>{numberText(item.partial_absences)}</td><td>{numberText(item.unexcused_absences)}</td><td>{numberText(item.awol)}</td><td>{item.handbook_action}</td></tr>)}{items.length === 0 ? <tr><td colSpan={7}>No attendance records for this month.</td></tr> : null}</tbody></table></div></section>
      </div>
    </Shell>
  );
}
