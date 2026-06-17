import Link from "next/link";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getPayrollRuns } from "@/lib/api";

const groups = [
  {
    title: "Readiness",
    items: [
      { href: "/launch", label: "Launch", desc: "Health checks." },
      { href: "/backup", label: "Backups", desc: "Data safety." },
      { href: "/settings", label: "Settings", desc: "System info." },
      { href: "/controls/old-schedules", label: "Old schedules", desc: "Old schedule data notes." },
    ],
  },
  {
    title: "Payroll",
    items: [
      { href: "/cutoff", label: "Cutoff", desc: "Save draft." },
      { href: "/payroll/runs", label: "Runs", desc: "Review history." },
      { href: "/payroll", label: "Preview", desc: "Check totals." },
    ],
  },
];

export default async function OperationsControlsPage() {
  const runs = await getPayrollRuns();
  const recentRuns = runs.slice(0, 3);

  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Controls</span><h1>Payroll controls</h1><p className="muted">Key routes and recent runs.</p></div>
          <StatusBadge label="ready" tone="ok" />
        </header>
        <section className="grid cols-3">
          {groups.map((group) => (
            <div className="card" key={group.title}>
              <div className="panel-title"><h2>{group.title}</h2></div>
              <div className="action-list">
                {group.items.map((item) => (
                  <Link className="action-item" href={item.href} key={item.href}><strong>{item.label}</strong><p className="muted">{item.desc}</p></Link>
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
