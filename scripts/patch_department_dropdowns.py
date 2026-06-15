from __future__ import annotations

from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not find expected block for: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    helper = '''\n\ndef department_names(include_blank: bool = False) -> list[str]:\n    rows = fetchall(conn, "SELECT name FROM departments WHERE active=1 ORDER BY name")\n    names = [r["name"] for r in rows]\n    if include_blank:\n        return [""] + names\n    return names or ["General"]\n\n\ndef department_index(value: str, options: list[str]) -> int:\n    if value in options:\n        return options.index(value)\n    if value and value not in options:\n        execute(conn, "INSERT OR IGNORE INTO departments(name, active) VALUES(?,1)", (value,))\n        options.append(value)\n        return len(options) - 1\n    return 0\n'''
    if "def department_names(include_blank: bool = False)" not in text:
        text = replace_once(
            text,
            '''def require_roles(*roles: str) -> bool:\n    if has_role(*roles):\n        return True\n    st.error("You do not have permission for this action.")\n    audit(current_user, "Denied permission", "app_users", int(st.session_state["auth_user"]["id"]), f"required={roles}; role={current_role}")\n    return False\n''',
            '''def require_roles(*roles: str) -> bool:\n    if has_role(*roles):\n        return True\n    st.error("You do not have permission for this action.")\n    audit(current_user, "Denied permission", "app_users", int(st.session_state["auth_user"]["id"]), f"required={roles}; role={current_role}")\n    return False\n''' + helper,
            "department helper functions",
        )

    text = replace_once(
        text,
        '''            dept = col3.selectbox("Department", [d["name"] for d in fetchall(conn, "SELECT name FROM departments WHERE active=1 ORDER BY name")])\n''',
        '''            dept = col3.selectbox("Department", department_names())\n''',
        "add employee department dropdown source",
    )

    text = replace_once(
        text,
        '''                dept = c2.text_input("Department", emp["department"])\n''',
        '''                dept_options = department_names()\n                dept = c2.selectbox("Department", dept_options, index=department_index(emp["department"], dept_options))\n''',
        "edit employee department dropdown",
    )

    text = replace_once(
        text,
        '''                department = st.text_input("Department / Area", value="")\n''',
        '''                dept_options = department_names(include_blank=True)\n                employee_department = fetchone(conn, "SELECT department FROM employees WHERE id=?", (opts[emp_label],))\n                default_dept = (employee_department or {}).get("department") or ""\n                department = st.selectbox("Department / Area", dept_options, index=department_index(default_dept, dept_options))\n''',
        "schedule department dropdown",
    )

    old_dept_tab = '''    with tabs[3]:\n        with st.form("dept"):\n            name = st.text_input("Department Name")\n            if st.form_submit_button("Add Department") and name:\n                execute(conn, "INSERT OR IGNORE INTO departments(name, active) VALUES(?,1)", (name,))\n                st.success("Department saved.")\n        show_table("Departments", "SELECT name, active FROM departments ORDER BY name")\n'''
    new_dept_tab = '''    with tabs[3]:\n        st.subheader("Departments")\n        st.caption("Use one clean department list for Staff/Payroll now, and for Operations/Staff App syncing later. Avoid free-typed variants like Cafe/Café/Kitchen Cafe.")\n        with st.form("dept"):\n            c1, c2 = st.columns([3, 1])\n            name = c1.text_input("Department Name")\n            active = c2.checkbox("Active", value=True)\n            if st.form_submit_button("Save Department") and name:\n                execute(\n                    conn,\n                    "INSERT INTO departments(name, active) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET active=excluded.active",\n                    (name.strip(), int(active)),\n                )\n                audit(current_user, "Saved department", "departments", None, name.strip())\n                st.success("Department saved.")\n                st.rerun()\n        dept_rows = fetchall(conn, "SELECT id, name, active FROM departments ORDER BY active DESC, name")\n        st.dataframe(pd.DataFrame(dept_rows), use_container_width=True, hide_index=True)\n'''
    text = replace_once(text, old_dept_tab, new_dept_tab, "settings department manager")

    APP_PATH.write_text(text, encoding="utf-8")
    print("Patched app.py department dropdowns and department manager.")


if __name__ == "__main__":
    main()
