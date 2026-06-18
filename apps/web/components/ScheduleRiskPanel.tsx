type ShiftLike = {
  id: number;
  employee_id: number | null;
  employee_name?: string | null;
  shift_date: string;
  start_time: string;
  end_time: string;
  position?: string | null;
  is_overnight?: boolean;
};

type EmployeeLike = {
  id: number;
  full_name: string;
  department?: string;
  position?: string;
};

function minutes(time: string) {
  const [h, m] = time.split(":").map(Number);
  return (Number(h) || 0) * 60 + (Number(m) || 0);
}

function normalizedRange(shift: ShiftLike) {
  const start = minutes(shift.start_time || "00:00");
  let end = minutes(shift.end_time || "00:00");
  if (end <= start || shift.is_overnight) end += 24 * 60;
  return { start, end };
}

function overlaps(a: ShiftLike, b: ShiftLike) {
  const first = normalizedRange(a);
  const second = normalizedRange(b);
  return first.start < second.end && second.start < first.end;
}

export function ScheduleRiskPanel({ days, shifts, employees }: { days: string[]; shifts: ShiftLike[]; employees: EmployeeLike[] }) {
  const employeeById = new Map(employees.map((employee) => [employee.id, employee]));
  const conflicts: string[] = [];
  for (const employee of employees) {
    const employeeShifts = shifts.filter((shift) => shift.employee_id === employee.id);
    for (let i = 0; i < employeeShifts.length; i += 1) {
      for (let j = i + 1; j < employeeShifts.length; j += 1) {
        const a = employeeShifts[i];
        const b = employeeShifts[j];
        if (a.shift_date === b.shift_date && overlaps(a, b)) {
          conflicts.push(`${employee.full_name} has overlapping shifts on ${a.shift_date}.`);
        }
      }
    }
  }

  const uncoveredDays = days.filter((day) => shifts.filter((shift) => shift.shift_date === day).length === 0);
  const noSecurity = days.filter((day) => !shifts.some((shift) => shift.shift_date === day && String(shift.position || employeeById.get(Number(shift.employee_id))?.position || "").toLowerCase().includes("security")));
  const noReception = days.filter((day) => !shifts.some((shift) => shift.shift_date === day && String(shift.position || employeeById.get(Number(shift.employee_id))?.position || "").toLowerCase().includes("reception")));
  const nightCoverage = days.filter((day) => !shifts.some((shift) => shift.shift_date === day && (shift.is_overnight || minutes(shift.end_time || "00:00") <= minutes(shift.start_time || "00:00") || minutes(shift.end_time || "00:00") >= 22 * 60)));

  const notes = [
    ...conflicts.slice(0, 4),
    ...uncoveredDays.slice(0, 3).map((day) => `No scheduled shifts on ${day}.`),
    ...noSecurity.slice(0, 3).map((day) => `No security coverage tagged on ${day}.`),
    ...noReception.slice(0, 3).map((day) => `No reception coverage tagged on ${day}.`),
    ...nightCoverage.slice(0, 3).map((day) => `No evening or overnight coverage tagged on ${day}.`),
  ].slice(0, 8);

  return (
    <section className="card">
      <div className="panel-title">
        <div><h2>Coverage Review</h2><p className="muted">Coverage gaps and schedule conflicts.</p></div>
        <div className="badge-row">
          <span className={conflicts.length ? "badge danger" : "badge ok"}>{conflicts.length ? `${conflicts.length} conflict(s)` : "No conflicts"}</span>
          <span className={notes.length ? "badge warning" : "badge ok"}>{notes.length ? `${notes.length} item(s)` : "Clear"}</span>
        </div>
      </div>
      <div className="action-list">
        {notes.length ? notes.map((note) => <div className="action-item" key={note}><strong>{note}</strong></div>) : <p className="muted">No coverage issues for the current filters.</p>}
      </div>
    </section>
  );
}
