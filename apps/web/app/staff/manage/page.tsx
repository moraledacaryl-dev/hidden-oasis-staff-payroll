import Link from "next/link";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { getEmployees } from "@/lib/api";
import { apiBaseUrl, backendHeaders } from "@/lib/backend";
import type { Employee } from "@/lib/types";
import { currentSession } from "@/lib/session";

const read = (data: FormData, key: string) => String(data.get(key) || "").trim();

async function saveEmployee(id: number | null, data: FormData) {
  "use server";
  const session = await currentSession();
  if (!session || !["owner", "payroll", "supervisor"].includes(session.role_key)) throw new Error("Not permitted.");
  const numberOrNull = (key: string) => read(data, key) ? Number(read(data, key)) : null;
  const canEditBenefits = ["owner", "payroll"].includes(session.role_key);
  const body = {
    employee_code: read(data, "employee_code"),
    full_name: read(data, "full_name"),
    department_name: read(data, "department_name") || null,
    position: read(data, "position") || null,
    employment_type: read(data, "employment_type") || null,
    status: read(data, "status") || "Active",
    default_shift_start: read(data, "default_shift_start") || null,
    default_shift_end: read(data, "default_shift_end") || null,
    standard_shift_hours: numberOrNull("standard_shift_hours"),
    unpaid_break_minutes: numberOrNull("unpaid_break_minutes"),
    ...(canEditBenefits ? {
      benefits_sss: data.get("benefits_sss") ? 1 : 0,
      benefits_philhealth: data.get("benefits_philhealth") ? 1 : 0,
      benefits_pagibig: data.get("benefits_pagibig") ? 1 : 0,
      benefits_tax: data.get("benefits_tax") ? 1 : 0,
    } : {}),
  };
  const response = await fetch(`${apiBaseUrl()}/api/v1/staff/employees${id ? `/${id}` : ""}`, {
    method: "POST",
    cache: "no-store",
    body: JSON.stringify(body),
    headers: await backendHeaders(true),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "Unable to save employee.");
  }
  revalidatePath("/staff");
  revalidatePath("/staff/manage");
  redirect("/staff");
}

function Fields({ item, canEditBenefits }: { item?: Employee; canEditBenefits: boolean }) {
  return <div className="form-grid">
    <label>Code<input name="employee_code" defaultValue={item?.employee_code || ""} required /></label>
    <label>Full name<input name="full_name" defaultValue={item?.full_name || ""} required /></label>
    <label>Department<input name="department_name" defaultValue={item?.department_name || ""} /></label>
    <label>Position<input name="position" defaultValue={item?.position || ""} /></label>
    <label>Type<select name="employment_type" defaultValue={item?.employment_type || "Regular"}><option>Regular</option><option>Probationary</option><option>Part-time</option><option>Freelance</option><option>Seasonal</option></select></label>
    <label>Status<select name="status" defaultValue={item?.status || "Active"}><option>Active</option><option>Inactive</option><option>On Leave</option><option>Separated</option></select></label>
    <label>Shift start<input type="time" name="default_shift_start" defaultValue={item?.default_shift_start || ""} /></label>
    <label>Shift end<input type="time" name="default_shift_end" defaultValue={item?.default_shift_end || ""} /></label>
    <label>Shift hours<input type="number" min="0" max="24" step="0.25" name="standard_shift_hours" defaultValue={item?.standard_shift_hours ?? ""} /></label>
    <label>Break minutes<input type="number" min="0" max="1440" name="unpaid_break_minutes" defaultValue={item?.unpaid_break_minutes ?? ""} /></label>
    {canEditBenefits ? <label className="check-field"><input type="checkbox" name="benefits_sss" defaultChecked={Boolean(item?.benefits_sss)} />SSS</label> : null}
    {canEditBenefits ? <label className="check-field"><input type="checkbox" name="benefits_philhealth" defaultChecked={Boolean(item?.benefits_philhealth)} />PhilHealth</label> : null}
    {canEditBenefits ? <label className="check-field"><input type="checkbox" name="benefits_pagibig" defaultChecked={Boolean(item?.benefits_pagibig)} />Pag-IBIG</label> : null}
    {canEditBenefits ? <label className="check-field"><input type="checkbox" name="benefits_tax" defaultChecked={Boolean(item?.benefits_tax)} />Tax</label> : null}
  </div>;
}

export default async function ManageStaffPage({ searchParams }: { searchParams: Promise<{ employee?: string; add?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) redirect("/staff");
  const canEditBenefits = ["owner", "payroll"].includes(session.role_key);
  const params = await searchParams;
  const selectedEmployeeId = Number(params.employee || 0) || null;
  const addOpen = params.add === "1";
  const employees = await getEmployees();

  return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page">
    <header className="page-header"><div className="grid"><span className="eyebrow">Staff</span><h1>Manage employees</h1><div className="action-row"><Link className="button ghost" href="/staff">Staff directory</Link></div></div></header>
    <details id="add-employee" className="card" open={addOpen}><summary><strong>Add employee</strong></summary><form action={saveEmployee.bind(null, null)} className="grid" style={{marginTop:14}}><Fields canEditBenefits={canEditBenefits} /><button className="primary-button" type="submit">Add employee</button></form></details>
    <section className="grid">{employees.map(item => <details id={`employee-${item.id}`} className="card" key={item.id} open={selectedEmployeeId === item.id}><summary><strong>{item.full_name}</strong> · {item.employee_code} · {item.status}</summary><form action={saveEmployee.bind(null, item.id)} className="grid" style={{marginTop:14}}><Fields item={item} canEditBenefits={canEditBenefits} /><div className="action-row"><button className="primary-button" type="submit">Save changes</button><Link className="button ghost" href="/staff">Cancel</Link></div></form></details>)}</section>
  </div></Shell>;
}
