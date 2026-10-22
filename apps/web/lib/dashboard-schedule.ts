import type { ScheduleShift } from "./schedule-types";

/** Planned shifts starting on the business date, grouped without counting split shifts twice. */
export function scheduledToday(items: ScheduleShift[], today: string) {
  const shifts = items.filter((shift) => shift.shift_date === today)
    .sort((a, b) => a.start_time.localeCompare(b.start_time));
  const people = new Map<number, { employeeId: number; name: string; department: string; shifts: ScheduleShift[] }>();
  for (const shift of shifts) {
    if (shift.employee_id == null) continue;
    const person = people.get(shift.employee_id) || {
      employeeId: shift.employee_id,
      name: shift.employee_name || "Employee",
      department: shift.employee_department || shift.department || "",
      shifts: [],
    };
    if (!person.shifts.some((existing) => existing.start_time === shift.start_time && existing.end_time === shift.end_time)) {
      person.shifts.push(shift);
    }
    people.set(shift.employee_id, person);
  }
  return { people: [...people.values()], unassigned: shifts.filter((shift) => shift.employee_id == null).length };
}
