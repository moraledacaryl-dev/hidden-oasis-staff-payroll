"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { RoleKey } from "@/lib/types";

type PayrollAction = "lock" | "approve" | "paid" | "reopen";

export function PayrollLifecycleButtons({ runId, status, role = "owner" }: { runId: number; status: string; role?: RoleKey }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reopenOpen, setReopenOpen] = useState(false);
  const [reopenReason, setReopenReason] = useState("");
  const [reopenConfirm, setReopenConfirm] = useState("");

  async function submit(action: PayrollAction, options: { reason?: string; confirmation?: string } = {}) {
    if (action === "paid" && !window.confirm("Mark this payroll run as paid? This applies cash advance repayments and reduces outstanding balances.")) return;

    if (action === "reopen") {
      const reason = String(options.reason || "").trim();
      const confirmation = String(options.confirmation || "").trim();

      if (reason.length < 10) {
        setMessage("Enter a reopen reason with at least 10 characters.");
        return;
      }

      if (confirmation !== "REOPEN PAYROLL") {
        setMessage("Type REOPEN PAYROLL to confirm reopening.");
        return;
      }
    }

    setBusy(action);
    setMessage(null);

    const response = await fetch("/api/payroll/lifecycle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: runId,
        action,
        reason: options.reason || "",
        confirmation: options.confirmation || "",
      }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.message || "Action failed.");
      setBusy(null);
      return;
    }

    setMessage("Saved.");
    setBusy(null);
    setReopenOpen(false);
    setReopenReason("");
    setReopenConfirm("");
    router.refresh();
  }

  return (
    <div className="payroll-lifecycle-control">
      <div className="action-row">
        {status === "Draft" ? (
          <button className="button small" disabled={!!busy} onClick={() => submit("lock")}>
            {busy === "lock" ? "Locking..." : "Lock"}
          </button>
        ) : null}

        {role === "owner" && status === "For Owner Review" ? (
          <button className="button small" disabled={!!busy} onClick={() => submit("approve")}>
            {busy === "approve" ? "Approving..." : "Approve"}
          </button>
        ) : null}

        {role === "owner" && status === "Approved" ? (
          <button className="button small" disabled={!!busy} onClick={() => submit("paid")}>
            {busy === "paid" ? "Marking paid..." : "Mark Paid"}
          </button>
        ) : null}

        {role === "owner" && (status === "For Owner Review" || status === "Approved" || status === "Paid") ? (
          <button className="button small ghost" disabled={!!busy} onClick={() => setReopenOpen(true)}>
            {busy === "reopen" ? "Reopening..." : "Reopen"}
          </button>
        ) : null}

        {message ? <span className="muted">{message}</span> : null}
      </div>

      {reopenOpen ? (
        <section className="reopen-confirm-card">
          <div>
            <strong>Reopen payroll run</strong>
            <p className="muted">This unlocks a reviewed or finalized payroll run. Record a clear reason before continuing.</p>
          </div>

          <label>
            <span>Reason for reopening</span>
            <textarea
              rows={3}
              value={reopenReason}
              onChange={(event) => setReopenReason(event.target.value)}
              placeholder="Example: Attendance correction after review"
              required
            />
          </label>

          <label>
            <span>Type REOPEN PAYROLL</span>
            <input
              value={reopenConfirm}
              onChange={(event) => setReopenConfirm(event.target.value)}
              placeholder="REOPEN PAYROLL"
              required
            />
          </label>

          <div className="action-row">
            <button
              className="button ghost"
              type="button"
              disabled={!!busy}
              onClick={() => {
                setReopenOpen(false);
                setReopenReason("");
                setReopenConfirm("");
              }}
            >
              Cancel
            </button>

            <button
              className="button danger"
              type="button"
              disabled={!!busy || reopenReason.trim().length < 10 || reopenConfirm.trim() !== "REOPEN PAYROLL"}
              onClick={() => submit("reopen", { reason: reopenReason, confirmation: reopenConfirm })}
            >
              {busy === "reopen" ? "Reopening..." : "Confirm reopen"}
            </button>
          </div>
        </section>
      ) : null}

      <style jsx>{`
        .payroll-lifecycle-control {
          display: grid;
          gap: 12px;
        }

        .reopen-confirm-card {
          display: grid;
          gap: 12px;
          padding: 14px;
          border: 1px solid var(--danger);
          border-radius: 8px;
          background: var(--surface);
        }

        .reopen-confirm-card label {
          display: grid;
          gap: 6px;
        }

        .reopen-confirm-card label > span {
          color: var(--muted);
          font-size: .7rem;
          font-weight: 850;
          text-transform: uppercase;
          letter-spacing: .065em;
        }

        .reopen-confirm-card textarea {
          resize: vertical;
        }
      `}</style>
    </div>
  );
}
