"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { AttendanceException } from "@/lib/api";
import styles from "./AttendanceDecisionPanel.module.css";

type Decision = "Approve" | "Reject" | "Excused" | "Unexcused";

type Props = {
  item: AttendanceException;
  triggerLabel?: string;
};

const decisions: Array<{ value: Decision; label: string; detail: string }> = [
  { value: "Approve", label: "Approve record", detail: "Accept the attendance and current OT values." },
  { value: "Reject", label: "Return for correction", detail: "Keep it unresolved and require correction." },
  { value: "Excused", label: "Mark excused", detail: "Record the exception without attendance penalty." },
  { value: "Unexcused", label: "Mark unexcused", detail: "Record the exception as an attendance infraction." },
];

export function AttendanceDecisionPanel({ item, triggerLabel = "Review" }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState<Decision>("Approve");
  const [reason, setReason] = useState("");
  const [approvedOt, setApprovedOt] = useState(String(item.approved_ot_hours || 0));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!open) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  async function submit() {
    const cleanReason = reason.trim();
    if (decision !== "Approve" && cleanReason.length < 8) {
      setMessage("Enter a reason with at least 8 characters for this decision.");
      setSuccess(false);
      return;
    }
    setBusy(true);
    setMessage("");
    setSuccess(false);
    const response = await fetch("/api/attendance/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        time_log_id: item.id,
        decision,
        reason: cleanReason || "Reviewed and approved from the attendance queue.",
        approved_ot_hours: Number(approvedOt || 0),
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Decision was not saved.");
      return;
    }
    setMessage("Attendance decision saved.");
    setSuccess(true);
    router.refresh();
  }

  return (
    <>
      <button className={styles.trigger} type="button" onClick={() => setOpen(true)}>{triggerLabel}</button>
      {open ? (
        <div className={styles.backdrop} role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setOpen(false); }}>
          <section className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby={`attendance-decision-${item.id}`}>
            <header className={styles.head}>
              <div>
                <span className="eyebrow">Employee-day decision</span>
                <h2 id={`attendance-decision-${item.id}`}>{item.full_name}</h2>
                <p>{item.work_date} · {item.department || "No department"} · {item.position || "No position"}</p>
              </div>
              <button className="button ghost small" type="button" onClick={() => setOpen(false)}>Close</button>
            </header>

            <div className={styles.summary}>
              <div className={styles.fact}><span>Actual in</span><strong>{item.actual_in || "Missing"}</strong></div>
              <div className={styles.fact}><span>Actual out</span><strong>{item.actual_out || "Missing"}</strong></div>
              <div className={styles.fact}><span>Status</span><strong>{item.attendance_status || "Needs Review"}</strong></div>
              <div className={styles.fact}><span>Detected OT</span><strong>{Number(item.detected_ot_hours || 0).toFixed(2)} h</strong></div>
              <div className={styles.fact}><span>Absence</span><strong>{item.is_absent ? item.absence_type || "Absent" : "No"}</strong></div>
              <div className={styles.fact}><span>OT status</span><strong>{item.ot_status || "None"}</strong></div>
            </div>

            {item.notes ? <div className={styles.warning}><strong>Existing note:</strong> {item.notes}</div> : null}

            <div className={styles.form}>
              <div>
                <span className="eyebrow">Decision</span>
                <div className={styles.choiceGrid}>
                  {decisions.map((option) => (
                    <button key={option.value} className={`${styles.choice} ${decision === option.value ? styles.active : ""}`} type="button" onClick={() => setDecision(option.value)}>
                      <strong>{option.label}</strong>
                      <span>{option.detail}</span>
                    </button>
                  ))}
                </div>
              </div>

              <label>Approved OT hours<input type="number" min="0" step="0.25" value={approvedOt} onChange={(event) => setApprovedOt(event.target.value)} /></label>
              <label>Decision reason<textarea rows={4} value={reason} onChange={(event) => setReason(event.target.value)} placeholder={decision === "Approve" ? "Optional approval note" : "Required explanation"} /></label>

              {message ? <div className={`${styles.message} ${success ? styles.success : styles.error}`}>{message}</div> : null}

              <div className={styles.actions}>
                <button className="button ghost" type="button" disabled={busy} onClick={() => setOpen(false)}>Cancel</button>
                <button className="button" type="button" disabled={busy} onClick={submit}>{busy ? "Saving…" : "Save decision"}</button>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
