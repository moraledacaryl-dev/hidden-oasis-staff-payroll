import assert from "node:assert/strict";
import test from "node:test";
import { scheduledToday } from "../lib/dashboard-schedule.ts";

const shift = (overrides = {}) => ({ id: 1, employee_id: 1, employee_name: "Jamie Reyes", employee_department: "Reception", shift_date: "2026-10-22", start_time: "08:00", end_time: "12:00", position: "Receptionist", break_minutes: 0, status: "Scheduled", planned_paid_hours: 4, is_overnight: false, ...overrides });

test("today's roster excludes other dates and unassigned shifts from employee count", () => {
  const result = scheduledToday([shift(), shift({ id: 2, shift_date: "2026-10-21" }), shift({ id: 3, employee_id: null }), shift({ id: 4, employee_id: 2, shift_date: "2026-10-23" })], "2026-10-22");
  assert.equal(result.people.length, 1);
  assert.equal(result.unassigned, 1);
  assert.equal(result.people[0].department, "Reception");
});

test("split shifts remain visible under one employee, duplicate rows are not repeated", () => {
  const items = [shift({ id: 2, start_time: "14:00", end_time: "18:00" }), shift(), shift({ id: 3 })];
  const result = scheduledToday(items, "2026-10-22");
  assert.equal(result.people.length, 1);
  assert.deepEqual(result.people[0].shifts.map(s => s.start_time), ["08:00", "14:00"]);
  assert.equal(items[0].start_time, "14:00");
});

test("overnight shift keeps its next-day flag and belongs to its start date", () => {
  const night = shift({ start_time: "22:00", end_time: "06:00", is_overnight: true });
  assert.equal(scheduledToday([night], "2026-10-22").people[0].shifts[0].is_overnight, true);
  assert.deepEqual(scheduledToday([night], "2026-10-23"), { people: [], unassigned: 0 });
});
