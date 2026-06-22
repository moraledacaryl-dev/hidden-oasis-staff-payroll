from __future__ import annotations

from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "schedule" / "page.tsx"

OLD_OPTIONS = '''  const scheduledEmployeeIds = new Set(enrichedItems.map((item) => item.employee_id).filter((id): id is number => typeof id === "number"));
  const employeeOptions = employees.filter((employee) => scheduledEmployeeIds.has(employee.id) || employees.length <= 80).sort((a, b) => a.full_name.localeCompare(b.full_name));'''

NEW_OPTIONS = '''  const employeeOptions = [...employees].sort((a, b) => a.full_name.localeCompare(b.full_name));'''

OLD_BOARD = '''  const boardEmployeeIds = new Set(filteredItems.map((item) => item.employee_id).filter((id): id is number => typeof id === "number"));
  const boardEmployees = employees.filter((employee) => { const byDepartment = selectedDepartment === "all" || employee.department === selectedDepartment; const byPosition = selectedPosition === "all" || employee.position === selectedPosition || filteredItems.some((item) => item.employee_id === employee.id && item.position === selectedPosition); const byEmployee = selectedEmployeeNumber == null || employee.id === selectedEmployeeNumber; return byDepartment && byPosition && byEmployee && (boardEmployeeIds.has(employee.id) || selectedEmployeeNumber === employee.id); }).sort((a, b) => a.full_name.localeCompare(b.full_name));'''

NEW_BOARD = '''  const boardEmployees = employees.filter((employee) => { const byDepartment = selectedDepartment === "all" || employee.department === selectedDepartment; const byPosition = selectedPosition === "all" || employee.position === selectedPosition || filteredItems.some((item) => item.employee_id === employee.id && item.position === selectedPosition); const byEmployee = selectedEmployeeNumber == null || employee.id === selectedEmployeeNumber; return byDepartment && byPosition && byEmployee; }).sort((a, b) => a.full_name.localeCompare(b.full_name));'''


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    updated = text

    if OLD_OPTIONS in updated:
        updated = updated.replace(OLD_OPTIONS, NEW_OPTIONS)
    elif NEW_OPTIONS not in updated:
        raise RuntimeError("Could not find the employee-options visibility block.")

    if OLD_BOARD in updated:
        updated = updated.replace(OLD_BOARD, NEW_BOARD)
    elif NEW_BOARD not in updated:
        raise RuntimeError("Could not find the schedule-board employee visibility block.")

    if updated == text:
        print("Schedule employee visibility is already fixed.")
        return

    TARGET.write_text(updated, encoding="utf-8")
    print(f"Updated {TARGET}")
    print("All active employees now remain visible across schedule weeks.")


if __name__ == "__main__":
    main()
