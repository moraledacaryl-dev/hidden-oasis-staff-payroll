"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { AppUser } from "@/lib/api";
import type { Employee } from "@/lib/types";

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
    if (!createResponse.ok || !created.ok || !created.user_id) { setCreating(false); setMessage(typeof created.detail === "string" ? created.detail : created.message || "User creation failed."); return; }
    const userId = Number(created.user_id);
    const resetResponse = await fetch(`/api/settings/users/${userId}/reset-password`, { method: "POST" });
    const reset = await resetResponse.json().catch(() => ({}));
    if (!resetResponse.ok || !reset.ok) { setCreating(false); setMessage(typeof reset.detail === "string" ? reset.detail : reset.message || "User was created, but password generation failed."); router.refresh(); return; }
    const activeResponse = await fetch(`/api/settings/users/${userId}/active`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active: true }) });
    const activated = await activeResponse.json().catch(() => ({}));
    setCreating(false); setTemporaryPassword(reset.temporary_password || "");
    if (!activeResponse.ok || !activated.ok) { setMessage("User and temporary password were created, but the account is still inactive."); router.refresh(); return; }
    setMessage("User created and activated. Copy the temporary password now."); setDisplayName(""); setEmployeeId(""); setRole("Staff"); router.refresh();
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

  return (
    <div className="grid">
      <section className="card soft">
        <div className="panel-title"><div><span className="eyebrow">Owner only</span><h2>Create user</h2><p className="muted">The login name is what the user enters on the sign-in screen.</p></div></div>
        <div className="form-grid">
          <label><span>Login name</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Employee login name" /></label>
          <label><span>Role</span><select value={role} onChange={(event) => setRole(event.target.value)}><option value="Staff">Staff</option><option value="Supervisor">Supervisor</option><option value="Payroll">Payroll</option><option value="Owner">Owner</option></select></label>
          <label><span>Employee</span><select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}><option value="">Not linked</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
        </div>
        <div className="action-row"><button className="button" type="button" disabled={creating} onClick={createUser}>{creating ? "Creating…" : "Create user"}</button></div>
      </section>
      {temporaryPassword ? (
        <section className="card soft">
          <span className="eyebrow">Show once</span>
          <h2>Temporary password</h2>
          <p className="copy-box">{temporaryPassword}</p>
          <p className="muted">Shown once. Not stored in plaintext.</p>
        </section>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}
      <div className="table-wrap">
        <table>
          <thead><tr><th>User</th><th>Role</th><th>Employee</th><th>Active</th><th>Must change</th><th>Last login</th><th>Actions</th></tr></thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.display_name}</td>
                <td>{user.role}</td>
                <td>
                  <select defaultValue={user.employee_id || ""} disabled={busy === user.id} onChange={(event) => setEmployee(user.id, event.target.value)}>
                    <option value="">Not linked</option>
                    {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}
                  </select>
                </td>
                <td>{user.active ? "Yes" : "No"}</td>
                <td>{user.must_change_password ? "Yes" : "No"}</td>
                <td>{user.last_login_at || "—"}</td>
                <td>
                  <div className="action-row">
                    <button className="button small ghost" type="button" disabled={busy === user.id} onClick={() => resetPassword(user.id)}>Reset password</button>
                    <button className="button small ghost" type="button" disabled={busy === user.id} onClick={() => setActive(user.id, !user.active)}>{user.active ? "Deactivate" : "Activate"}</button>
                  </div>
                </td>
              </tr>
            ))}
            {!users.length ? <tr><td colSpan={7}>No app users found.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
