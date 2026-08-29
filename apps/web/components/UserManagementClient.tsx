"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { AppUser } from "@/lib/api";
import { defaultPathForRole } from "@/lib/session-client";
import type { Employee } from "@/lib/types";
import type { RoleKey } from "@/lib/types";

export function UserManagementClient({ users, employees }: { users: AppUser[]; employees: Employee[] }) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState("Staff");
  const [employeeId, setEmployeeId] = useState("");

  async function createUser() {
    if (!displayName.trim()) { setMessage("Enter a login name."); return; }
    setCreating(true); setMessage(""); setTemporaryPassword("");
    const createResponse = await fetch("/api/settings/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name: displayName.trim(), role, employee_id: employeeId ? Number(employeeId) : null }) });
    const created = await createResponse.json().catch(() => ({}));
    setCreating(false);
    if (!createResponse.ok || !created.ok) {
      setMessage(typeof created.detail === "string" ? created.detail : created.message || "User creation failed.");
      return;
    }
    setTemporaryPassword(created.temporary_password || "");
    setMessage("User created.");
    setDisplayName("");
    setEmployeeId("");
    setRole("Staff");
    router.refresh();
  }

  async function resetPassword(userId: number) {
    setBusy(userId);
    setMessage("");
    setTemporaryPassword("");
    const response = await fetch(`/api/settings/users/${userId}/reset-password`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Password reset failed.");
      return;
    }
    setTemporaryPassword(data.temporary_password || "");
    setMessage("Temporary password generated. Show it once.");
    router.refresh();
  }

  async function setActive(userId: number, active: boolean) {
    setBusy(userId);
    setMessage("");
    const response = await fetch(`/api/settings/users/${userId}/active`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "User update failed.");
      return;
    }
    setMessage("User updated.");
    router.refresh();
  }

  async function setEmployee(userId: number, employeeId: string) {
    setBusy(userId);
    setMessage("");
    const response = await fetch(`/api/settings/users/${userId}/employee`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employee_id: employeeId ? Number(employeeId) : null }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Employee link failed.");
      return;
    }
    setMessage("Employee link saved.");
    router.refresh();
  }

  async function setRoleForUser(userId: number, nextRole: string) {
    setBusy(userId);
    setMessage("");
    const response = await fetch(`/api/settings/users/${userId}/role`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: nextRole }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Role update failed.");
      return;
    }
    setMessage("Role updated.");
    router.refresh();
  }

  async function viewAs(user: AppUser) {
    setBusy(user.id);
    setMessage("");
    const response = await fetch("/api/session/impersonate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_user_id: user.id }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Could not open this account view.");
      setBusy(null);
      return;
    }
    window.location.assign(defaultPathForRole(data.user.role_key as RoleKey));
  }

  return (
    <div className="grid">
      <section className="card">
        <div className="panel-title"><div><span className="eyebrow">Owner only</span><h2>Create user</h2></div></div>
        <div className="form-grid">
          <label><span>Login name</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Employee login name" /></label>
          <label><span>Role</span><select value={role} onChange={(event) => setRole(event.target.value)}><option value="Staff">Staff</option><option value="General Manager">General Manager</option><option value="Payroll">Payroll</option><option value="Owner">Owner</option></select></label>
          <label><span>Employee</span><select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}><option value="">Not linked</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
        </div>
        <div className="action-row"><button className="button" type="button" disabled={creating} onClick={createUser}>{creating ? "Creating…" : "Create user"}</button></div>
      </section>
      {temporaryPassword ? (
        <section className="card soft">
          <span className="eyebrow">Show once</span>
          <h2>Temporary password</h2>
          <p className="copy-box">{temporaryPassword}</p>
        </section>
      ) : null}
      {message ? <p className="muted" role="status">{message}</p> : null}
      <div className="table-wrap user-table">
        <table>
          <thead><tr><th>User</th><th>Role</th><th>Employee</th><th>Active</th><th>Password</th><th>MFA</th><th>Last login</th><th>Actions</th></tr></thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.display_name}</td>
                <td>
                  <select aria-label={`Role for ${user.display_name}`} defaultValue={user.role_key} disabled={busy === user.id} onChange={(event) => setRoleForUser(user.id, event.target.value)}>
                    <option value="staff">Staff</option>
                    <option value="supervisor">General Manager</option>
                    <option value="payroll">Payroll</option>
                    <option value="owner">Owner</option>
                  </select>
                </td>
                <td>
                  <select aria-label={`Employee linked to ${user.display_name}`} defaultValue={user.employee_id || ""} disabled={busy === user.id} onChange={(event) => setEmployee(user.id, event.target.value)}>
                    <option value="">Not linked</option>
                    {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}
                  </select>
                </td>
                <td>{user.active ? "Yes" : "No"}</td>
                <td>{user.must_change_password ? "Change required" : "Set"}</td>
                <td>{user.mfa_enabled ? "On" : "Off"}</td>
                <td>{user.last_login_at || "—"}</td>
                <td>
                  <div className="action-row">
                    <button className="button small ghost" type="button" disabled={busy === user.id} onClick={() => resetPassword(user.id)}>Reset password</button>
                    <button className="button small ghost" type="button" disabled={busy === user.id} onClick={() => setActive(user.id, !user.active)}>{user.active ? "Deactivate" : "Activate"}</button>
                    {user.active && (user.role_key === "supervisor" || (user.role_key === "staff" && user.employee_id)) ? (
                      <button
                        className="button small"
                        data-view-as-role={user.role_key}
                        type="button"
                        disabled={busy === user.id}
                        onClick={() => viewAs(user)}
                      >
                        {busy === user.id ? "Opening..." : "View as"}
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
            {!users.length ? <tr><td colSpan={8}>No users found.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
