import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { PageHeading, SectionBody, SectionCard, SectionHeader, Toolbar } from "@/components/UiPrimitives";
import { getEmployees } from "@/lib/api";
import { currentSession } from "@/lib/session";

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "—";
}

function normalize(value: string | null | undefined) {
  return String(value || "").trim().toLowerCase();
}

export default async function StaffPage({ searchParams }: { searchParams: Promise<{ q?: string; status?: string; department?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;

  const params = await searchParams;
  const employees = await getEmployees();
  const canEdit = ["owner", "payroll", "supervisor"].includes(session.role_key);
  const showPrivate = session.role_key === "owner" || session.role_key === "payroll";
  const query = normalize(params.q);
  const status = params.status || "current";
  const department = params.department || "all";
  const currentStatuses = new Set(["Active", "On Leave", "Probationary"]);
  const filtered = employees.filter((employee) => {
    const matchesQuery = !query || [employee.full_name, employee.employee_code, employee.position, employee.department_name].some((value) => normalize(value).includes(query));
    const matchesStatus = status === "all" || (status === "current" ? currentStatuses.has(employee.status) : !currentStatuses.has(employee.status));
    const matchesDepartment = department === "all" || (employee.department_name || "Unassigned") === department;
    return matchesQuery && matchesStatus && matchesDepartment;
  });
  const active = employees.filter((employee) => employee.status === "Active").length;
  const onLeave = employees.filter((employee) => employee.status === "On Leave").length;
  const former = employees.filter((employee) => !currentStatuses.has(employee.status)).length;
  const freelance = employees.filter((employee) => employee.employment_type === "Freelance").length;
  const departments = Array.from(new Set(employees.map((employee) => employee.department_name || "Unassigned"))).sort();

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page people-page">
        <PageHeading eyebrow="People" title="Staff directory" description="One operational identity per worker across scheduling, attendance, HR, and payroll." actions={canEdit ? <><Link className="button secondary" href="/staff/manage">Manage records</Link><Link className="button" href="/staff/manage?add=1#add-employee">Add employee</Link></> : undefined} />

        <section className="people-kpis">
          <div className="people-kpi"><span>Active staff</span><strong>{active}</strong></div>
          <div className="people-kpi"><span>On leave</span><strong>{onLeave}</strong></div>
          <div className="people-kpi"><span>Former workers retained</span><strong>{former}</strong></div>
          <div className="people-kpi"><span>Freelance records</span><strong>{freelance}</strong></div>
        </section>

        <SectionCard>
          <Toolbar>
            <form className="people-filter" action="/staff">
              <label>Search<input name="q" placeholder="Name, code, role, or department" defaultValue={params.q || ""} /></label>
              <label>Lifecycle<select name="status" defaultValue={status}><option value="current">Current workers</option><option value="former">Former workers</option><option value="all">All records</option></select></label>
              <label>Department<select name="department" defaultValue={department}><option value="all">All departments</option>{departments.map((item) => <option key={item}>{item}</option>)}</select></label>
              <button className="button" type="submit">Apply</button>
            </form>
            <div className="people-tabs"><Link aria-current={status === "current" ? "page" : undefined} href="/staff?status=current">Current</Link><Link aria-current={status === "former" ? "page" : undefined} href="/staff?status=former">Former</Link><Link aria-current={status === "all" ? "page" : undefined} href="/staff?status=all">All</Link></div>
          </Toolbar>
        </SectionCard>

        <section className="people-directory">
          <div className="people-directory-head"><div><h2>Workers</h2><p>{filtered.length} of {employees.length} records shown</p></div><StatusBadge label={canEdit ? "Editable" : "View only"} tone={canEdit ? "ok" : "warning"} /></div>
          <div className="people-table-wrap">
            <table className="people-table">
              <thead><tr><th>Worker</th><th>Department</th><th>Role</th><th>Engagement</th><th>Lifecycle</th><th>Default shift</th>{showPrivate ? <th>Benefits</th> : null}{canEdit ? <th /> : null}</tr></thead>
              <tbody>
                {filtered.map((employee) => <tr key={employee.id}>
                  <td><div className="people-identity"><span className="people-avatar">{initials(employee.full_name)}</span><div><strong>{employee.full_name}</strong><small>{employee.employee_code}</small></div></div></td>
                  <td>{employee.department_name || "Unassigned"}</td>
                  <td>{employee.position || "—"}</td>
                  <td>{employee.employment_type || "—"}</td>
                  <td><StatusBadge label={employee.status} tone={employee.status === "Active" ? "ok" : employee.status === "On Leave" ? "warning" : "neutral"} /></td>
                  <td>{employee.default_shift_start || "—"}–{employee.default_shift_end || "—"}</td>
                  {showPrivate ? <td><div className="badge-row">{employee.benefits_sss ? <span className="badge">SSS</span> : null}{employee.benefits_philhealth ? <span className="badge">PhilHealth</span> : null}{employee.benefits_pagibig ? <span className="badge">Pag-IBIG</span> : null}{employee.benefits_tax ? <span className="badge">Tax</span> : null}</div></td> : null}
                  {canEdit ? <td><div className="people-actions"><Link className="button small ghost" href={`/staff/manage?employee=${employee.id}#employee-${employee.id}`}>Open</Link></div></td> : null}
                </tr>)}
                {!filtered.length ? <tr><td colSpan={canEdit ? (showPrivate ? 8 : 7) : (showPrivate ? 7 : 6)}><div className="people-empty">No worker records match these filters.</div></td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="people-card-grid">
          <SectionCard><SectionHeader title="People operations" description="Related records and management workspaces." /><SectionBody><div className="people-list"><Link className="people-list-row" href="/performance-reviews"><span><strong>Performance reviews</strong><span>Annual reviews and follow-up records</span></span><strong>Open →</strong></Link><Link className="people-list-row" href="/hr"><span><strong>HR and leave</strong><span>Entitlements, requests, and formal records</span></span><strong>Open →</strong></Link></div></SectionBody></SectionCard>
          <SectionCard><SectionHeader title="Financial support" description="Employee balances that connect to payroll." /><SectionBody><div className="people-list"><Link className="people-list-row" href="/cash-advances"><span><strong>Cash advances</strong><span>Requests, balances, and repayments</span></span><strong>Open →</strong></Link></div></SectionBody></SectionCard>
        </section>
      </div>
    </Shell>
  );
}
