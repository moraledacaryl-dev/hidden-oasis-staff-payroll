import Link from "next/link";
import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { getEmployees } from "@/lib/api";
import { currentSession } from "@/lib/session";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";

const API = (process.env.STAFF_PAYROLL_API_URL || process.env.NEXT_PUBLIC_STAFF_PAYROLL_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
const read = (data: FormData, key: string) => String(data.get(key) || "").trim();

async function saveEmployee(id: number | null, data: FormData) {
  "use server";
  const session = await currentSession();
  if (!session || !["owner", "payroll"].includes(session.role_key)) throw new Error("Not permitted.");
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  const numberOrNull = (key: string) => read(data, key) ? Number(read(data, key)) : null;
  const body = {
    employee_code: read(data, "employee_code"),
    full_name: read(data, "full_name"),
    department_name: read(data, "department_name") || null,
    position: read(data, "position") || null,
    employment_type: read(data, "employment_type") || null,
    status: read(data, "status") || "Active",
    default_shift_start: read(data, "default_shift_start") || null,
    default_shift_end: read(data, "default_shift_end") || null,
    standard_paid_hours: numberOrNull("standard_paid_hours"),
    break_mins: numberOrNull("break_mins"),
    benefits_sss: data.get("benefits_sss") ? 1 : 0,
    benefits_philhealth: data.get("benefits_philhealth") ? 1 : 0,
    benefits_pagibig: data.get("benefits_pagibig") ? 1 : 0,
    benefits_tax: data.get("benefits_tax") ? 1 : 0,
  };
  const response = await fetch(`${API}/api/v1/staff/employees${id ? `/${id}` : ""}`, {
    method: "POST",
    cache: "no-store",
    body: JSON.stringify(body),
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "Unable to save employee.");
  }
  revalidatePath("/staff");
  revalidatePath("/staff/manage");
  redirect("/staff");
}

function Fields({ item }: { item?: any }) {
  return <div className="form-grid">
    <label>Code<input name="employee_code" defaultValue={item?.employee_code || ""} required /></label>
    <label>Full name<input name="full_name" defaultValue={item?.full_name || ""} required /></label>
    <label>Department<input name="department_name" defaultValue={item?.department_name || ""} /></label>
    <label>Position<input name="position" defaultValue={item?.position || ""} /></label>
    <label>Type<select name="employment_type" defaultValue={item?.employment_type || "Regular"}><option>Regular</option><option>Probationary</option><option>Part-time</option><option>Freelance</option><option>Seasonal</option></select></label>
    <label>Status<select name="status" defaultValue={item?.status || "Active"}><option>Active</option><option>Inactive</option><option>On Leave</option><option>Separated</option></select></label>
    <label>Shift start<input type="time" name="default_shift_start" defaultValue={item?.default_shift_start || ""} /></label>
    <label>Shift end<input type="time" name="default_shift_end" defaultValue={item?.default_shift_end || ""} /></label>
    <label>Paid hours<input type="number" min="0" step="0.25" name="standard_paid_hours" defaultValue={item?.standard_paid_hours ?? ""} /></label>
    <label>Break minutes<input type="number" min="0" name="break_mins" defaultValue={item?.break_mins ?? ""} /></label>
    <label className="check-field"><input type="checkbox" name="benefits_sss" defaultChecked={Boolean(item?.benefits_sss)} />SSS</label>
    <label className="check-field"><input type="checkbox" name="benefits_philhealth" defaultChecked={Boolean(item?.benefits_philhealth)} />PhilHealth</label>
    <label className="check-field"><input type="checkbox" name="benefits_pagibig" defaultChecked={Boolean(item?.benefits_pagibig)} />Pag-IBIG</label>
    <label className="check-field"><input type="checkbox" name="benefits_tax" defaultChecked={Boolean(item?.benefits_tax)} />Tax</label>
  </div>;
}

export default async function ManageStaffPage({ searchParams }: { searchParams: Promise<{ employee?: string; add?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll"].includes(session.role_key)) redirect("/staff");
  const params = await searchParams;
  const selectedEmployeeId = Number(params.employee || 0) || null;
  const addOpen = params.add === "1";
  const employees = await getEmployees();

  return <Shell allowedRoles={["owner", "payroll"]}><div className="page">
    <header className="page-header"><div className="grid"><span className="eyebrow">Staff</span><h1>Manage employees</h1><p className="muted">Add, edit, or deactivate employee records without removing their history.</p><div className="action-row"><Link className="button ghost" href="/staff">Back to staff directory</Link></div></div></header>
    <details id="add-employee" className="card" open={addOpen}><summary><strong>Add employee</strong></summary><form action={saveEmployee.bind(null, null)} className="grid" style={{marginTop:14}}><Fields /><button className="primary-button" type="submit">Add employee</button></form></details>
    <section className="grid">{employees.map(item => <details id={`employee-${item.id}`} className="card" key={item.id} open={selectedEmployeeId === item.id}><summary><strong>{item.full_name}</strong> · {item.employee_code} · {item.status}</summary><form action={saveEmployee.bind(null, item.id)} className="grid" style={{marginTop:14}}><Fields item={item} /><div className="action-row"><button className="primary-button" type="submit">Save changes</button><Link className="button ghost" href="/staff">Cancel</Link></div></form></details>)}</section>
  </div></Shell>;
}
