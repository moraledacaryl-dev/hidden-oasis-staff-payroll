import Link from "next/link";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRuns } from "@/lib/api";
import { currentSession } from "@/lib/session";
import { redirect } from "next/navigation";

const groups = [
  {
    title: "Readiness",
    items: [
      { href: "/launch", label: "Launch" },
      { href: "/backup", label: "Backups" },
      { href: "/settings", label: "Settings" },
      { href: "/controls/old-schedules", label: "Old schedules" },
    ],
  },
  {
    title: "Payroll",
    items: [
      { href: "/cutoff", label: "Cutoff" },
      { href: "/payroll/runs", label: "Runs" },
      { href: "/payroll", label: "Preview" },
    ],
  },
];

export default async function OperationsControlsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll"]}><div /></Shell>;
  const runs = await getPayrollRuns();
  const recentRuns = runs.slice(0, 3);

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Controls</span><h1>Payroll controls</h1></div>
          <StatusBadge label={`${recentRuns.length} recent`} tone="ok" />
        </header>
        <section className="grid cols-3">
          {groups.map((group) => (
            <div className="card" key={group.title}>
              <div className="panel-title"><h2>{group.title}</h2></div>
              <div className="action-list">
                {group.items.map((item) => (
                  <Link className="action-item" href={item.href} key={item.href}><strong>{item.label}</strong></Link>
                ))}
              </div>
            </div>
          ))}
          <div className="card">
            <div className="panel-title"><h2>Recent runs</h2></div>
            <div className="action-list">
              {recentRuns.map((run) => (
                <Link className="action-item" href={`/payroll/runs/${run.id}`} key={run.id}>
                  <strong>Run #{run.id}</strong>
                  <p className="muted">{run.status} · {run.period_start} to {run.period_end}</p>
                </Link>
              ))}
              {!recentRuns.length ? <p className="muted">No saved runs.</p> : null}
            </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
