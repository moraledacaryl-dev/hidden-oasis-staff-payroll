"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export type Holiday = { id: number; holiday_date: string; name: string; holiday_type: "Regular Holiday" | "Special Non-Working Day"; active: boolean; notes?: string | null };

type FormState = Omit<Holiday, "id">;
const emptyForm: FormState = { holiday_date: "", name: "", holiday_type: "Regular Holiday", active: true, notes: "" };

export function HolidayManager({ holidays }: { holidays: Holiday[] }) {
  const router = useRouter();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  function edit(item: Holiday) { setEditingId(item.id); setForm({ holiday_date: item.holiday_date, name: item.name, holiday_type: item.holiday_type, active: item.active, notes: item.notes || "" }); setMessage(""); }
  function reset() { setEditingId(null); setForm(emptyForm); setMessage(""); }

  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    const path = editingId ? `/api/payroll/holidays/${editingId}` : "/api/payroll/holidays";
    const response = await fetch(path, { method: editingId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
    const data = await response.json().catch(() => ({})); setBusy(false);
    if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : data.message || "Holiday could not be saved."); return; }
    setMessage(editingId ? "Holiday updated." : "Holiday added."); setEditingId(null); setForm(emptyForm); router.refresh();
  }

  async function toggle(item: Holiday) {
    setBusy(true); setMessage("");
    const response = await fetch(`/api/payroll/holidays/${item.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ holiday_date: item.holiday_date, name: item.name, holiday_type: item.holiday_type, active: !item.active, notes: item.notes || "" }) });
    const data = await response.json().catch(() => ({})); setBusy(false);
    if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : "Holiday status could not be changed."); return; }
    router.refresh();
  }

  return <div className="grid" style={{ gap: 24 }}>
    <section className="card"><h2>{editingId ? "Edit holiday" : "Add holiday"}</h2><p className="muted">Payroll applies the selected classification to this exact calendar date. Use only the controlled classifications below.</p>
      <form className="grid" style={{ gap: 14 }} onSubmit={save}>
        <label>Date<input required type="date" value={form.holiday_date} onChange={(e) => setForm({ ...form, holiday_date: e.target.value })} /></label>
        <label>Holiday name<input required maxLength={160} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Classification<select value={form.holiday_type} onChange={(e) => setForm({ ...form, holiday_type: e.target.value as FormState["holiday_type"] })}><option>Regular Holiday</option><option>Special Non-Working Day</option></select></label>
        <label><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Active for payroll</label>
        <label>Notes<textarea maxLength={500} value={form.notes || ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        <div className="action-row"><button className="button" disabled={busy} type="submit">{busy ? "Saving…" : editingId ? "Save changes" : "Add holiday"}</button>{editingId ? <button className="button ghost" type="button" onClick={reset}>Cancel</button> : null}</div>
        {message ? <p role="status">{message}</p> : null}
      </form>
    </section>
    <section className="card"><h2>Holiday calendar</h2><p className="muted">Inactive dates remain visible for auditability but do not affect new payroll calculations.</p>
      <div className="table-scroll"><table><thead><tr><th>Date</th><th>Name</th><th>Classification</th><th>Status</th><th>Actions</th></tr></thead><tbody>{holidays.map((item) => <tr key={item.id}><td>{item.holiday_date}</td><td>{item.name}</td><td>{item.holiday_type}</td><td>{item.active ? "Active" : "Inactive"}</td><td><div className="action-row"><button className="button ghost" type="button" onClick={() => edit(item)}>Edit</button><button className="button ghost" disabled={busy} type="button" onClick={() => toggle(item)}>{item.active ? "Deactivate" : "Activate"}</button></div></td></tr>)}{holidays.length === 0 ? <tr><td colSpan={5}>No holidays configured yet.</td></tr> : null}</tbody></table></div>
    </section>
  </div>;
}
