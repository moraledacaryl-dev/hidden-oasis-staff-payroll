"use client";

import { useEffect, useState } from "react";

type Publication = {
  status?: string;
  published_by?: string | null;
  published_at?: string | null;
  notes?: string | null;
};

export function SchedulePublishControl({ weekStart }: { weekStart: string }) {
  const [publication, setPublication] = useState<Publication | null>(null);
  const [notes, setNotes] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadPublication() {
    const response = await fetch("/api/schedule/shifts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation: "get_schedule_publication", week_start: weekStart }),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok && data.ok) {
      setPublication(data.publication || null);
      if (data.publication?.notes) setNotes(String(data.publication.notes));
    }
  }

  useEffect(() => {
    void loadPublication();
  }, [weekStart]);

  async function publish() {
    const confirmed = window.confirm(
      publication
        ? "Republish this schedule week? Staff will continue to see the updated published schedule."
        : "Publish this schedule week? Staff assigned to this week will be able to see it."
    );
    if (!confirmed) return;

    setBusy(true);
    setMessage("");
    const response = await fetch("/api/schedule/shifts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation: "publish_schedule", week_start: weekStart, notes: notes || null }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);

    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Schedule publication failed.");
      return;
    }

    setPublication(data.publication || null);
    setMessage(publication ? "Schedule republished." : "Schedule published. Staff can now see this week.");
  }

  const published = publication?.status === "Published";

  return (
    <section className="card soft">
      <div className="panel-title">
        <div>
          <span className="eyebrow">Publication</span>
          <h2>{published ? "Published schedule" : "Draft schedule"}</h2>
          <p className="muted">
            {published
              ? `Published${publication?.published_by ? ` by ${publication.published_by}` : ""}${publication?.published_at ? ` on ${publication.published_at}` : ""}.`
              : "Staff cannot see this week until it is published."}
          </p>
        </div>
        <span className={`status-badge ${published ? "ok" : "warning"}`}>{published ? "Published" : "Draft"}</span>
      </div>

      <label>
        <span>Publication note</span>
        <input
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Optional note for this publication"
        />
      </label>

      <div className="action-row">
        <button className="button" type="button" disabled={busy} onClick={publish}>
          {busy ? "Publishing…" : published ? "Republish schedule" : "Publish schedule"}
        </button>
      </div>

      {message ? <p className="muted">{message}</p> : null}
    </section>
  );
}
