import Link from "next/link";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";

const groups = [
  {
    title: "Launch readiness",
    items: [
      { href: "/launch", label: "Launch Center", desc: "System health and launch checklist." },
      { href: "/backup", label: "Backup Center", desc: "Backup locations and recovery reminders." },
      { href: "/settings", label: "Settings", desc: "Migration and configuration reference." },
    ],
  },
  {
    title: "Payroll review",
    items: [
      { href: "/cutoff", label: "Cutoff Control", desc: "Draft and review cutoff readiness." },
      { href: "/payroll/runs", label: "Run History", desc: "Open saved payroll runs." },
      { href: "/payroll", label: "Payroll Preview", desc: "Preview through the engine." },
    ],
  },
  {
    title: "Current run shortcuts",
    items: [
      { href: "/payroll/runs/1", label: "Review Run #1", desc: "Employee-level stored run detail." },
      { href: "/payroll/runs/1/reports", label: "Report Run #1", desc: "Earnings, deductions, and department totals." },
      { href: "/payroll/runs/1/audit", label: "Audit Run #1", desc: "Lifecycle timeline." },
      { href: "/payroll/runs/1/payslips", label: "Payslips Run #1", desc: "Printable employee copies." },
    ],
  },
];

export default async function OperationsControlsPage() {
  return (
    <Shell allowedRoles={["owner", "payroll"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid"><span className="eyebrow">Operations Controls</span><h1>Payroll Control Map</h1><p className="muted">One page for the migrated payroll routes while the sidebar remains conservative.</p></div>
          <StatusBadge label="read only" tone="ok" />
        </header>
        <section className="grid cols-3">
          {groups.map((group) => (
            <div className="card" key={group.title}>
              <div className="panel-title"><div><h2>{group.title}</h2><p className="muted">Quick access links.</p></div></div>
              <div className="action-list">
                {group.items.map((item) => (
                  <Link className="action-item" href={item.href} key={item.href}><strong>{item.label}</strong><p className="muted">{item.desc}</p></Link>
                ))}
              </div>
            </div>
          ))}
        </section>
      </div>
    </Shell>
  );
}
