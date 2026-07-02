"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type ReviewItem = {
  source_type: "schedule" | "attendance" | "shift_request";
  id: number;
  request_no?: string | null;
  title: string;
  subtitle: string;
  date?: string | null;
  status: string;
  issue_summary: string;
  detail?: string | null;
};

type ReviewResponse = {
  ok?: boolean;
  summary?: {
    total: number;
    schedule: number;
    attendance: number;
    shift_requests: number;
  };
  items?: ReviewItem[];
};

async function post(body: Record<string, unknown>) {
  const response = await fetch("/api/schedule/shifts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || "Request failed.");
  return data;
}

function sourceLabel(source: ReviewItem["source_type"]) {
  if (source === "schedule") return "Schedule";
  if (source === "attendance") return "Attendance upload";
  return "Staff request";
}

export function ScheduleChangeReview() {
  const router = useRouter();
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [summary, setSummary] = useState<ReviewResponse["summary"] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const data: ReviewResponse = await post({ operation: "review_queue" });
      setItems(data.items || []);
      setSummary(data.summary || null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load review queue.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function approve(item: ReviewItem, form: HTMLFormElement) {
    const decision = "Approved";
    const key = `${item.source_type}-${item.id}`;
    setBusy(key);
    setError("");

    const data = new FormData(form);
    const decision_note = String(data.get("decision_note") || "");
    const employee_notified = data.get("employee_notified") === "on";
    const coverage_confirmed = data.get("coverage_confirmed") === "on";
    const apply_change = data.get("apply_change") !== "off";

    try {
      if (item.source_type === "shift_request") {
        await post({
          operation: "decide_request",
          request_id: item.id,
          decision,
          decision_note,
          employee_notified,
          coverage_confirmed,
          apply_change,
        });
      } else {
        await post({
          operation: "decide_review_queue",
          source_type: item.source_type,
          item_id: item.id,
          decision,
          decision_note,
        });
      }
      await load();
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Decision failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid">
      <section className="card">
        <div className="panel-title">
          <div>
            <span className="eyebrow">Unified review queue</span>
            <h2>Needs Review</h2>
            <p className="muted">
              Schedule issues, attendance upload flags, and staff shift-change requests appear here.
            </p>
          </div>
          <button className="button secondary" type="button" onClick={() => window.print()}>
            Print queue
          </button>
        </div>
        {summary ? (
          <div className="grid cols-4">
            <div className="metric"><span className="eyebrow">Total</span><strong className="metric-value">{summary.total}</strong></div>
            <div className="metric"><span className="eyebrow">Schedule</span><strong className="metric-value">{summary.schedule}</strong></div>
            <div className="metric"><span className="eyebrow">Attendance</span><strong className="metric-value">{summary.attendance}</strong></div>
            <div className="metric"><span className="eyebrow">Requests</span><strong className="metric-value">{summary.shift_requests}</strong></div>
          </div>
        ) : null}
      </section>

      {error ? (
        <section className="card">
          <strong>Could not complete action</strong>
          <p className="muted">{error}</p>
        </section>
      ) : null}

      {items.map((item) => {
        const key = `${item.source_type}-${item.id}`;
        const isRequest = item.source_type === "shift_request";

        return (
          <article className="card shift-request-print" key={key}>
            <div className="panel-title">
              <div>
                <span className="eyebrow">{sourceLabel(item.source_type)} {item.request_no ? `· ${item.request_no}` : ""}</span>
                <h2>{item.title}</h2>
                <p className="muted">{item.subtitle}</p>
              </div>
              <strong>{item.status}</strong>
            </div>

            <div className="grid cols-2">
              <div>
                <strong>Issue / reason</strong>
                <p>{item.issue_summary || "Needs review."}</p>
              </div>
              <div>
                <strong>Details</strong>
                <p>{item.detail || "—"}</p>
              </div>
            </div>

            <form className="grid cols-2" onSubmit={(event) => event.preventDefault()}>
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                Decision note
                <textarea name="decision_note" rows={3} />
              </label>

              {isRequest ? (
                <>
                  <label><input type="checkbox" name="coverage_confirmed" /> Coverage confirmed</label>
                  <label><input type="checkbox" name="employee_notified" /> Employee notified</label>
                  <label><input type="checkbox" name="apply_change" defaultChecked /> Apply to schedule</label>
                </>
              ) : null}

              <div className="badge-row">
                <button
                  className="button"
                  type="button"
                  disabled={busy === key}
                  onClick={(event) => approve(item, event.currentTarget.form!)}
                >
                  Approve
                </button>
              </div>
            </form>
          </article>
        );
      })}

      {!items.length && !error ? (
        <section className="card">
          <p className="muted">No items need review.</p>
        </section>
      ) : null}
    </div>
  );
}
