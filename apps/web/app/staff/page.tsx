import { redirect } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { getEmployees } from "@/lib/api";
import { currentSession } from "@/lib/session";

export default async function StaffPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  }
  const employees = await getEmployees();
  const showPrivate = session?.role_key === "owner" || session?.role_key === "payroll";
  const active = employees.filter((employee) => employee.status === "Active");
  const freelance = employees.filter((employee) => employee.employment_type === "Freelance");
  const departments = new Set(employees.map((employee) => employee.department_name || "Unassigned"));

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Staff</span>
            <h1>Staff directory</h1>
            <p className="muted">Current employee records.</p>
          </div>
          <StatusBadge label="read only" tone="warning" />
        </header>
        <section className="grid cols-3">
          <MetricCard label="Active staff" value={active.length} detail="Status = Active" />
          <MetricCard label="Departments" value={departments.size} detail="Including unassigned" />
          <MetricCard label="Freelance records" value={freelance.length} detail="Manual output pay supported" />
        </section>
        <section className="card">
          <div className="panel-title"><div><h2>Employees</h2><p className="muted">{employees.length} records</p></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Code</th><th>Name</th><th>Department</th><th>Position</th><th>Type</th><th>Status</th><th>Default shift</th>{showPrivate ? <th>Benefits</th> : null}</tr></thead>
              <tbody>
                {employees.map((employee) => (
                  <tr key={employee.id}>
                    <td>{employee.employee_code}</td>
                    <td><strong>{employee.full_name}</strong></td>
                    <td>{employee.department_name || "—"}</td>
                    <td>{employee.position || "—"}</td>
                    <td>{employee.employment_type || "—"}</td>
                    <td>{employee.status}</td>
                    <td>{employee.default_shift_start || "—"}–{employee.default_shift_end || "—"}</td>
                    {showPrivate ? <td><div className="badge-row">{employee.benefits_sss ? <span className="badge">SSS</span> : null}{employee.benefits_philhealth ? <span className="badge">PhilHealth</span> : null}{employee.benefits_pagibig ? <span className="badge">Pag-IBIG</span> : null}{employee.benefits_tax ? <span className="badge">Tax</span> : null}</div></td> : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
