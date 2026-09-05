"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, Printer, Repeat2 } from "lucide-react";
import { AppDrawer, SurfaceContext, SurfaceSection } from "@/components/AppSurface";
import { StatusBadge } from "@/components/StatusBadge";

type Item = {
  id: number;
  request_no: string;
  employee_name: string;
  employee_code?: string;
  department?: string;
  request_type: string;
  original_date: string;
  original_start_time: string;
  original_end_time: string;
  requested_date?: string | null;
  requested_start_time?: string | null;
  requested_end_time?: string | null;
  reason: string;
  swap_employee_name?: string | null;
  status: string;
  emergency: number;
  submitted_at: string;
  reviewed_by_name?: string | null;
  decision_note?: string | null;
  employee_notified?: number;
  coverage_confirmed?: number;
  has_attachment?: boolean;
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

function toneForStatus(status: string): "ok" | "warning" | "danger" | "neutral" {
  if (status === "Approved") return "ok";
  if (status === "Rejected") return "danger";
  if (status === "Emergency Review") return "danger";
  if (status === "Pending") return "warning";
  return "neutral";
}

export function ScheduleChangeReview() {
  const router = useRouter();
  const [items, setItems] = useState<Item[]>([]);
  const [selected, setSelected] = useState<Item | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [decisionNote, setDecisionNote] = useState("");
  const [coverageConfirmed, setCoverageConfirmed] = useState(false);
  const [employeeNotified, setEmployeeNotified] = useState(false);
  const [applyChange, setApplyChange] = useState(true);

  const load = useCallback(async (selectedId?: number) => {
    try {
      const data = await post({ operation: "review_requests" });
      const nextItems: Item[] = data.items || [];
      setItems(nextItems);
      if (selectedId) setSelected(nextItems.find((item) => item.id === selectedId) || null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load requests.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const counts = useMemo(() => ({
    open: items.filter((item) => ["Pending", "Emergency Review"].includes(item.status)).length,
    emergency: items.filter((item) => Boolean(item.emergency) && ["Pending", "Emergency Review"].includes(item.status)).length,
    approved: items.filter((item) => item.status === "Approved").length,
    rejected: items.filter((item) => item.status === "Rejected").length,
  }), [items]);

  function openItem(item: Item) {
    setSelected(item);
    setDecisionNote(item.decision_note || "");
    setCoverageConfirmed(Boolean(item.coverage_confirmed));
    setEmployeeNotified(Boolean(item.employee_notified));
    setApplyChange(true);
  }

  async function decide(decision: "Approved" | "Rejected") {
    if (!selected) return;
    const selectedId = selected.id;
    setBusy(selectedId);
    setError("");
    try {
      await post({
        operation: "decide_request",
        request_id: selectedId,
        decision,
        decision_note: decisionNote,
        employee_notified: employeeNotified,
        coverage_confirmed: coverageConfirmed,
        apply_change: applyChange,
      });
      await load(selectedId);
      setSelected(null);
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Decision failed.");
    } finally {
      setBusy(null);
    }
  }

  const pending = selected ? ["Pending", "Emergency Review"].includes(selected.status) : false;
  const isSwap = selected?.request_type.trim().toLowerCase() === "shift swap";

  return (
    <div className="request-workspace">
      <div className="request-kpis">
        <div><Clock3 size={17} /><span>Open requests</span><strong>{counts.open}</strong></div>
        <div><AlertTriangle size={17} /><span>Emergency</span><strong>{counts.emergency}</strong></div>
        <div><CheckCircle2 size={17} /><span>Approved</span><strong>{counts.approved}</strong></div>
        <div><Repeat2 size={17} /><span>Rejected</span><strong>{counts.rejected}</strong></div>
      </div>

      <section className="request-queue-card">
        <header className="request-queue-head">
          <div><span className="eyebrow">Open first</span><h2>Request queue</h2><p>Review the original assignment, proposed change, coverage, and employee communication before deciding.</p></div>
          <button className="button secondary" type="button" onClick={() => window.print()}><Printer size={15} />Print requests</button>
        </header>

        {error ? <div className="request-error"><strong>Could not complete action</strong><span>{error}</span></div> : null}

        <div className="request-list">
          {items.map((item) => {
            const requestedDate = item.requested_date || item.original_date;
            const requestedStart = item.requested_start_time || item.original_start_time;
            const requestedEnd = item.requested_end_time || item.original_end_time;
            return (
              <button className="request-row" key={item.id} onClick={() => openItem(item)} type="button">
                <span className="request-avatar">{item.employee_name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("")}</span>
                <span className="request-person"><strong>{item.employee_name}</strong><small>{item.employee_code || "—"} · {item.department || "Unassigned"}</small></span>
                <span className="request-type"><strong>{item.request_type}</strong><small>{item.request_no}</small></span>
                <span className="request-shift"><small>Original</small><strong>{item.original_date}</strong><span>{item.original_start_time}–{item.original_end_time}</span></span>
                <ArrowRight className="request-arrow" size={16} />
                <span className="request-shift"><small>Requested</small><strong>{requestedDate}</strong><span>{requestedStart}–{requestedEnd}</span></span>
                <StatusBadge label={item.emergency ? `${item.status} · Emergency` : item.status} tone={toneForStatus(item.status)} />
              </button>
            );
          })}
          {!items.length && !error ? <div className="request-empty"><CheckCircle2 size={22} /><strong>No shift-change requests</strong><span>The queue is clear.</span></div> : null}
        </div>
      </section>

      <AppDrawer
        open={Boolean(selected)}
        eyebrow="Shift request"
        title={selected ? `${selected.request_type} · ${selected.employee_name}` : "Shift request"}
        description={selected ? `${selected.request_no} · submitted ${selected.submitted_at}` : undefined}
        onClose={() => setSelected(null)}
        footer={selected ? <><div>{pending ? <button className="button secondary" disabled={busy === selected.id} onClick={() => void decide("Rejected")} type="button">Reject</button> : null}</div><div className="badge-row"><button className="button ghost" onClick={() => setSelected(null)} type="button">Close</button>{pending ? <button className="button" disabled={busy === selected.id} onClick={() => void decide("Approved")} type="button">Approve request</button> : null}</div></> : null}
      >
        {selected ? <>
          <SurfaceContext>
            <div><span className="eyebrow">Employee</span><strong>{selected.employee_name}</strong><small>{selected.employee_code || "—"}</small></div>
            <div><span className="eyebrow">Department</span><strong>{selected.department || "Unassigned"}</strong><small>{selected.request_type}</small></div>
            <div><span className="eyebrow">Status</span><StatusBadge label={selected.emergency ? `${selected.status} · Emergency` : selected.status} tone={toneForStatus(selected.status)} /></div>
          </SurfaceContext>

          <SurfaceSection number="1" title="Assignment change" description="Compare the published shift and the requested replacement.">
            <div className="request-change-grid">
              <div><span>Original shift</span><strong>{selected.original_date}</strong><small>{selected.original_start_time}–{selected.original_end_time}</small></div>
              <ArrowRight size={18} />
              <div><span>Requested shift</span><strong>{selected.requested_date || selected.original_date}</strong><small>{selected.requested_start_time || selected.original_start_time}–{selected.requested_end_time || selected.original_end_time}</small></div>
            </div>
            {selected.swap_employee_name ? <p className="request-note">Swap with <strong>{selected.swap_employee_name}</strong>. Approval exchanges both shift assignments together.</p> : null}
          </SurfaceSection>

          <SurfaceSection number="2" title="Employee reason" description="Reason and supporting evidence submitted with the request.">
            <p className="request-reason">{selected.reason}</p>
            {selected.has_attachment ? <p className="request-note">A supporting document is attached to this request.</p> : null}
          </SurfaceSection>

          {pending ? <SurfaceSection number="3" title="Decision controls" description="Confirm coverage and communication before applying the change.">
            <label className="field">Decision note<textarea rows={4} value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} /></label>
            <div className="request-checks">
              <label><input type="checkbox" checked={coverageConfirmed} onChange={(event) => setCoverageConfirmed(event.target.checked)} />Coverage confirmed</label>
              <label><input type="checkbox" checked={employeeNotified} onChange={(event) => setEmployeeNotified(event.target.checked)} />Employee notified</label>
              <label><input type="checkbox" checked={applyChange} onChange={(event) => setApplyChange(event.target.checked)} />Apply approved change to schedule</label>
            </div>
            {isSwap ? <p className="request-note">This request updates both employees’ assignments as one transaction.</p> : null}
          </SurfaceSection> : <SurfaceSection number="3" title="Decision record" description="Recorded review outcome for this request."><p className="request-reason">{selected.decision_note || "No decision note recorded."}</p><div className="request-record"><span>Reviewed by <strong>{selected.reviewed_by_name || "management"}</strong></span><span>Coverage {selected.coverage_confirmed ? "confirmed" : "not recorded"}</span><span>Employee notification {selected.employee_notified ? "recorded" : "not recorded"}</span></div></SurfaceSection>}
        </> : null}
      </AppDrawer>
    </div>
  );
}
