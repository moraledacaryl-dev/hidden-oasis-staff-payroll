"use client";

import { useEffect, useState } from "react";

type Publication = {
  status?: string;
  published_by?: string | null;
  published_at?: string | null;
  notes?: string | null;
};

type State = {
  publication: Publication | null;
  pending: boolean;
};

export function SchedulePublicationPanel({ weekStart }: { weekStart: string }) {
  const [state, setState] = useState<State>({ publication: null, pending: false });
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refresh() {
    const response = await fetch("/api/schedule/shifts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation: "get_schedule_publication", week_start: weekStart }),
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) return;
    setState({ publication: data.publication || null, pending: Boolean(data.has_pending_changes) });
    if (data.publication?.notes) setNotes(String(data.publication.notes));
  }

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [weekStart]);

  async function publish() {
    const republish = Boolean(state.publication);
    const confirmed = window.confirm(
      republish
        ? "Republish this week so staff can see the latest revisions?"
        : "Publish this week so staff can see it?"
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
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Publication failed.");
      return;
    }

    setState({ publication: data.publication || null, pending: false });
    setMessage(republish ? "Revised schedule published." : "Schedule published.");
  }

  const published = state.publication?.status === "Published";
  const label = state.pending ? "Changes Pending" : published ? "Published" : "Draft";

  return (
    <section className="card soft">
      <div className="panel-title">
        <div>
          <span className="eyebrow">Publication</span>
          <h2>{label}</h2>
          <p className="muted">
            {!published
              ? "Staff cannot see this week until it is published."
              : state.pending
                ? "Staff still see the last published version until this week is republished."
                : `Published${state.publication?.published_by ? ` by ${state.publication.published_by}` : ""}${state.publication?.published_at ? ` on ${state.publication.published_at}` : ""}.`}
          </p>
        </div>
        <span className={`status-badge ${state.pending ? "warning" : published ? "ok" : "warning"}`}>{label}</span>
      </div>

      <label>
        <span>{state.pending ? "Revision note" : "Publication note"}</span>
        <input
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder={state.pending ? "Explain the revision" : "Optional publication note"}
        />
      </label>

      <div className="action-row">
        <button className="button" type="button" disabled={busy || (published && !state.pending)} onClick={publish}>
          {busy ? "Publishing…" : state.pending ? "Republish revised schedule" : published ? "Published" : "Publish schedule"}
        </button>
      </div>

      {message ? <p className="muted">{message}</p> : null}
    </section>
  );
}

export const SchedulePublishControl = SchedulePublicationPanel;
