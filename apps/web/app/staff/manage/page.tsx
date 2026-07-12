import Link from "next/link";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { PageHeading, SectionBody, SectionCard, SectionHeader } from "@/components/UiPrimitives";
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
  return <>
    <section className="app-surface-section">
      <header className="app-surface-section-header"><span>1</span><div><h3>Worker identity</h3><p>Core identity and organizational assignment.</p></div></header>
      <div className="app-surface-section-body staff-drawer-grid">
        <label>Code<input name="employee_code" defaultValue={item?.employee_code || ""} required /></label>
        <label>Full name<input name="full_name" defaultValue={item?.full_name || ""} required /></label>
        <label>Department<input name="department_name" defaultValue={item?.department_name || ""} /></label>
        <label>Position<input name="position" defaultValue={item?.position || ""} /></label>
        <label>Engagement type<select name="employment_type" defaultValue={item?.employment_type || "Regular"}><option>Regular</option><option>Probationary</option><option>Part-time</option><option>Freelance</option><option>Seasonal</option></select></label>
        <label>Lifecycle status<select name="status" defaultValue={item?.status || "Active"}><option>Active</option><option>Inactive</option><option>On Leave</option><option>Separated</option></select></label>
      </div>
    </section>

    <section className="app-surface-section">
      <header className="app-surface-section-header"><span>2</span><div><h3>Schedule defaults</h3><p>Default work pattern used when creating shifts.</p></div></header>
      <div className="app-surface-section-body staff-drawer-grid">
        <label>Shift start<input type="time" name="default_shift_start" defaultValue={item?.default_shift_start || ""} /></label>
        <label>Shift end<input type="time" name="default_shift_end" defaultValue={item?.default_shift_end || ""} /></label>
        <label>Shift hours<input type="number" min="0" max="24" step="0.25" name="standard_shift_hours" defaultValue={item?.standard_shift_hours ?? ""} /></label>
        <label>Break minutes<input type="number" min="0" max="1440" name="unpaid_break_minutes" defaultValue={item?.unpaid_break_minutes ?? ""} /></label>
      </div>
    </section>

    {canEditBenefits ? <section className="app-surface-section">
      <header className="app-surface-section-header"><span>3</span><div><h3>Payroll and benefits</h3><p>Restricted payroll participation settings.</p></div></header>
      <div className="app-surface-section-body staff-drawer-checks">
        <label><input type="checkbox" name="benefits_sss" defaultChecked={Boolean(item?.benefits_sss)} />SSS</label>
        <label><input type="checkbox" name="benefits_philhealth" defaultChecked={Boolean(item?.benefits_philhealth)} />PhilHealth</label>
        <label><input type="checkbox" name="benefits_pagibig" defaultChecked={Boolean(item?.benefits_pagibig)} />Pag-IBIG</label>
        <label><input type="checkbox" name="benefits_tax" defaultChecked={Boolean(item?.benefits_tax)} />Tax withholding</label>
      </div>
    </section> : null}
  </>;
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
  const selected = selectedEmployeeId ? employees.find((employee) => employee.id === selectedEmployeeId) : undefined;
  const drawerOpen = addOpen || Boolean(selected);

  return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div className="page people-page">
    <PageHeading eyebrow="People" title="Manage workers" description="Create and maintain worker identity, role, lifecycle, schedule defaults, and authorized payroll settings." actions={<><Link className="button secondary" href="/staff">Staff directory</Link><Link className="button" href="/staff/manage?add=1">Add worker</Link></>} />

    <SectionCard>
      <SectionHeader title="Worker records" description={`${employees.length} employee records. Open a worker to edit the canonical record.`} />
      <SectionBody><div className="staff-manage-list">{employees.map((item) => <div className="staff-manage-row" key={item.id}><div><strong>{item.full_name}</strong><small>{item.employee_code} · {item.department_name || "Unassigned"} · {item.status}</small></div><Link className="button small secondary" href={`/staff/manage?employee=${item.id}`}>Open record</Link></div>)}</div></SectionBody>
    </SectionCard>

    {drawerOpen ? <div className="app-surface-backdrop app-drawer-backdrop" role="presentation"><section className="app-surface app-drawer" role="dialog" aria-modal="true">
      <header className="app-surface-header"><div className="app-surface-heading"><span className="eyebrow">Worker record</span><h2>{selected ? selected.full_name : "Add worker"}</h2><p>{selected ? `${selected.employee_code} · ${selected.department_name || "Unassigned"}` : "Create the worker identity used by schedule, HR, attendance, and payroll."}</p></div><Link className="app-surface-close" aria-label="Close" href="/staff/manage">×</Link></header>
      <div className="app-surface-body"><form action={saveEmployee.bind(null, selected?.id || null)} className="staff-drawer-form" id="staff-record-form"><Fields item={selected} canEditBenefits={canEditBenefits} /></form></div>
      <footer className="app-surface-footer"><div /><div className="badge-row"><Link className="button ghost" href="/staff/manage">Cancel</Link><button className="button" form="staff-record-form" type="submit">{selected ? "Save changes" : "Add worker"}</button></div></footer>
    </section></div> : null}
  </div></Shell>;
}
