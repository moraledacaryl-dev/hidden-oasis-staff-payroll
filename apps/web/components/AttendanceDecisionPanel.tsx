"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppDrawer, SurfaceContext, SurfaceSection } from "@/components/AppSurface";
import { StatusBadge } from "@/components/StatusBadge";
import type { AttendanceException } from "@/lib/api";
import styles from "./AttendanceDecisionPanel.module.css";

type Decision = "Approve" | "Reject" | "Excused" | "Unexcused";
type Props = { item: AttendanceException; triggerLabel?: string };

const decisions: Array<{ value: Decision; label: string; detail: string }> = [
  { value: "Approve", label: "Approve record", detail: "Accept the attendance and current overtime values." },
  { value: "Reject", label: "Return for correction", detail: "Keep it unresolved and require a source correction." },
  { value: "Excused", label: "Mark excused", detail: "Record the exception without an attendance penalty." },
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

  async function submit() {
    const cleanReason = reason.trim();
    if (decision !== "Approve" && cleanReason.length < 8) {
      setMessage("Enter a reason with at least 8 characters for this decision.");
      setSuccess(false);
      return;
    }
    setBusy(true); setMessage(""); setSuccess(false);
    const response = await fetch("/api/attendance/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ time_log_id: item.id, decision, reason: cleanReason || "Reviewed and approved from the attendance queue.", approved_ot_hours: Number(approvedOt || 0) }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok || !data.ok) { setMessage(typeof data.detail === "string" ? data.detail : data.message || "Decision was not saved."); return; }
    setMessage("Attendance decision saved."); setSuccess(true); router.refresh();
  }

  return (
    <>
      <button className={styles.trigger} type="button" onClick={() => setOpen(true)}>{triggerLabel}</button>
      <AppDrawer
        open={open}
        eyebrow="Employee-day decision"
        title={item.full_name}
        description={`${item.work_date} · ${item.department || "No department"} · ${item.position || "No position"}`}
        onClose={() => setOpen(false)}
        footer={<><div>{message ? <span className={`${styles.message} ${success ? styles.success : styles.error}`}>{message}</span> : null}</div><div className="badge-row"><button className="button ghost" type="button" disabled={busy} onClick={() => setOpen(false)}>Cancel</button><button className="button" type="button" disabled={busy} onClick={() => void submit()}>{busy ? "Saving…" : "Save decision"}</button></div></>}
      >
        <SurfaceContext>
          <div><span className="eyebrow">Actual in</span><strong>{item.actual_in || "Missing"}</strong><small>{item.employee_code}</small></div>
          <div><span className="eyebrow">Actual out</span><strong>{item.actual_out || "Missing"}</strong><small>{Number(item.detected_ot_hours || 0).toFixed(2)} h detected OT</small></div>
          <div><span className="eyebrow">Detected state</span><StatusBadge label={item.is_absent ? item.absence_type || "Absent" : item.attendance_status || "Needs Review"} tone={item.is_absent ? "danger" : "warning"} /></div>
        </SurfaceContext>

        {item.notes ? <div className={styles.warning}><strong>Existing note:</strong> {item.notes}</div> : null}

        <SurfaceSection number="1" title="System-derived attendance" description="The system derives worked time, lateness, early out, partial attendance, missing punches, absence, and overtime from schedule and logs.">
          <div className={styles.summary}>
            <div className={styles.fact}><span>Status</span><strong>{item.attendance_status || "Needs Review"}</strong></div>
            <div className={styles.fact}><span>Absence</span><strong>{item.is_absent ? item.absence_type || "Absent" : "No"}</strong></div>
            <div className={styles.fact}><span>OT status</span><strong>{item.ot_status || "None"}</strong></div>
            <div className={styles.fact}><span>Detected OT</span><strong>{Number(item.detected_ot_hours || 0).toFixed(2)} h</strong></div>
          </div>
        </SurfaceSection>

        <SurfaceSection number="2" title="Supervisor decision" description="Choose the operational outcome. Non-approval decisions require a clear reason.">
          <div className={styles.choiceGrid}>{decisions.map((option) => <button key={option.value} className={`${styles.choice} ${decision === option.value ? styles.active : ""}`} type="button" onClick={() => setDecision(option.value)}><strong>{option.label}</strong><span>{option.detail}</span></button>)}</div>
        </SurfaceSection>

        <SurfaceSection number="3" title="Overtime and documentation" description="Confirm approved overtime and record the decision rationale.">
          <div className={styles.form}>
            <label>Approved OT hours<input type="number" min="0" step="0.25" value={approvedOt} onChange={(event) => setApprovedOt(event.target.value)} /></label>
            <label>Decision reason<textarea rows={4} value={reason} onChange={(event) => setReason(event.target.value)} placeholder={decision === "Approve" ? "Optional approval note" : "Required explanation"} /></label>
          </div>
        </SurfaceSection>
      </AppDrawer>
    </>
  );
}
