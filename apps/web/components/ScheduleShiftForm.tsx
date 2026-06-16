"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

const positions = ["Receptionist", "Cook", "Barista", "Bartender", "Security", "Housekeeper", "Other"];

type ScheduleEmployee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };

export function ScheduleShiftForm({ weekStart, employees }: { weekStart: string; employees: ScheduleEmployee[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState<string>("");
  const [busy, setBusy] = useState(false);

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");
    const employeeRaw = String(formData.get("employee_id") || "").trim();
    const payload = {
      employee_id: employeeRaw ? Number(employeeRaw) : null,
      shift_date: String(formData.get("shift_date") || weekStart),
      start_time: String(formData.get("start_time") || "08:00"),
      end_time: String(formData.get("end_time") || "17:00"),
      position: String(formData.get("position") || "Other"),
      department: String(formData.get("department") || "") || null,
      break_minutes: Number(formData.get("break_minutes") || 60),
      notes: String(formData.get("notes") || "") || null,
    };
    const res = await fetch("/api/schedule/shifts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await res.json().catch(() => ({}));
    setBusy(false);
    if (!res.ok || !data.ok) {
      setMessage(data.detail || data.message || "Shift was not saved.");
      return;
    }
    setMessage("Shift saved. Refreshing calendar…");
    const params = new URLSearchParams(searchParams.toString());
    params.set("week_start", weekStart);
    router.replace(`/schedule?${params.toString()}`);
    router.refresh();
  }

  return (
    <form action={submit} className="form-grid">
      <label>Date<input name="shift_date" type="date" defaultValue={weekStart} required /></label>
      <label>Employee<select name="employee_id" defaultValue=""><option value="">Unassigned shift</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name} · {employee.department || "No dept"} · {employee.position || "No position"}</option>)}</select></label>
      <label>Start<input name="start_time" type="time" defaultValue="08:00" required /></label>
      <label>End<input name="end_time" type="time" defaultValue="17:00" required /></label>
      <label>Position<select name="position" defaultValue="Receptionist">{positions.map((p) => <option key={p} value={p}>{p}</option>)}</select></label>
      <label>Department<input name="department" placeholder="Front Desk, Kitchen, Security…" /></label>
      <label>Break minutes<input name="break_minutes" type="number" min="0" defaultValue="60" /></label>
      <label>Notes<input name="notes" placeholder="Optional" /></label>
      <button className="primary-link" type="submit" disabled={busy}>{busy ? "Saving…" : "Add planned shift"}</button>
      {message ? <p className="muted">{message}</p> : null}
    </form>
  );
}
