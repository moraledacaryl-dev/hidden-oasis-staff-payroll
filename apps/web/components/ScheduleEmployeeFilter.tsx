"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type EmployeeOption = { id: number; full_name: string };

export function ScheduleEmployeeFilter({
  employees,
  selectedEmployeeId,
  weekStart,
  department,
  position,
}: {
  employees: EmployeeOption[];
  selectedEmployeeId: string;
  weekStart: string;
  department: string;
  position: string;
}) {
  const router = useRouter();
  const selected = employees.find((employee) => String(employee.id) === selectedEmployeeId);
  const [name, setName] = useState(selected?.full_name || "");

  function apply() {
    const employee = employees.find((item) => item.full_name.toLowerCase() === name.trim().toLowerCase());
    const query = new URLSearchParams({ week_start: weekStart });
    if (department !== "all") query.set("department", department);
    if (position !== "all") query.set("position", position);
    if (employee) query.set("employee_id", String(employee.id));
    router.push(`/schedule?${query.toString()}`);
  }

  return (
    <div className="form-grid">
      <label>
        Employee
        <input list="schedule-employees" value={name} onChange={(event) => setName(event.target.value)} placeholder="All employees" />
        <datalist id="schedule-employees">
          {employees.map((employee) => <option key={employee.id} value={employee.full_name} />)}
        </datalist>
      </label>
      <button className="button secondary" type="button" onClick={apply}>Apply</button>
      {selectedEmployeeId !== "all" ? <button className="button ghost" type="button" onClick={() => { setName(""); router.push(`/schedule?week_start=${weekStart}`); }}>Clear</button> : null}
    </div>
  );
}
