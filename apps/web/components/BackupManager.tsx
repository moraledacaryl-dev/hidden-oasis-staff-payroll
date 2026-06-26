"use client";

import { useCallback, useEffect, useState } from "react";

type Backup = {
  name: string;
  bytes: number;
  encrypted: boolean;
  created_at: string;
};

export function BackupManager() {
  const [items, setItems] = useState<Backup[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const response = await fetch("/api/production/backups", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(data.detail || "Backups could not be loaded.");
      return;
    }
    setItems(data.items || []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create() {
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/production/backups", { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage(data.detail || "Backup failed.");
      return;
    }
    setMessage("Backup created.");
    await load();
  }

  async function verify(name: string) {
    setBusy(true);
    setMessage("");
    const response = await fetch(`/api/production/backups/${encodeURIComponent(name)}/verify`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    setMessage(response.ok ? `${name} verified.` : data.detail || "Verification failed.");
  }

  return (
    <div className="grid">
      <div className="action-row">
        <button className="button" type="button" disabled={busy} onClick={create}>{busy ? "Working..." : "Create backup"}</button>
      </div>
      {message ? <p className="muted">{message}</p> : null}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Created</th><th>File</th><th>Size</th><th>Encryption</th><th>Actions</th></tr></thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.name}>
                <td>{item.created_at}</td>
                <td>{item.name}</td>
                <td>{Math.max(1, Math.round(item.bytes / 1024)).toLocaleString("en-PH")} KB</td>
                <td>{item.encrypted ? "Encrypted" : "Not encrypted"}</td>
                <td><div className="action-row"><button className="button small secondary" type="button" disabled={busy} onClick={() => verify(item.name)}>Verify</button><a className="button small ghost" href={`/api/production/backups/${encodeURIComponent(item.name)}/download`}>Download</a></div></td>
              </tr>
            ))}
            {!items.length ? <tr><td colSpan={5}>No backups yet.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
