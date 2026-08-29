"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AppModal } from "@/components/AppSurface";

type ConfirmActionModalProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
  busy?: boolean;
  danger?: boolean;
  children?: ReactNode;
  confirmationPhrase?: string;
};

export function ConfirmActionModal({
  open,
  title,
  description,
  confirmLabel,
  onConfirm,
  onClose,
  busy = false,
  danger = false,
  children,
  confirmationPhrase,
}: ConfirmActionModalProps) {
  const [typedConfirmation, setTypedConfirmation] = useState("");

  useEffect(() => {
    if (!open) setTypedConfirmation("");
  }, [open]);

  const phraseMatches = !confirmationPhrase || typedConfirmation.trim() === confirmationPhrase;

  return (
    <AppModal
      open={open}
      eyebrow="Confirm action"
      title={title}
      description={description}
      onClose={() => { if (!busy) onClose(); }}
      closeLabel={`Close ${title}`}
      footer={(
        <div className="action-row">
          <button className="button ghost" type="button" disabled={busy} onClick={onClose} autoFocus>
            Cancel
          </button>
          <button
            className={danger ? "button danger" : "button"}
            type="button"
            disabled={busy || !phraseMatches}
            onClick={() => void onConfirm()}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      )}
    >
      {children}
      {confirmationPhrase ? (
        <label>
          <span>Type {confirmationPhrase} to confirm</span>
          <input
            value={typedConfirmation}
            onChange={(event) => setTypedConfirmation(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            placeholder={confirmationPhrase}
          />
        </label>
      ) : null}
    </AppModal>
  );
}
