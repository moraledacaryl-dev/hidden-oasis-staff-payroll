"use client";

import { useEffect, useState } from "react";
import { AppModal } from "@/components/AppSurface";

type Props = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
  busy?: boolean;
  danger?: boolean;
  confirmationText?: string;
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
  confirmationText,
}: Props) {
  const [typed, setTyped] = useState("");

  useEffect(() => {
    if (!open) setTyped("");
  }, [open]);

  const requiresTypedConfirmation = Boolean(confirmationText);
  const canConfirm = !busy && (!requiresTypedConfirmation || typed.trim() === confirmationText);

  return (
    <AppModal
      open={open}
      eyebrow={danger ? "Confirm sensitive action" : "Confirm action"}
      title={title}
      description={description}
      onClose={() => { if (!busy) onClose(); }}
      closeLabel={`Cancel ${title.toLowerCase()}`}
      footer={(
        <div className="action-row">
          <button className="button ghost" disabled={busy} onClick={onClose} type="button" autoFocus={!requiresTypedConfirmation}>Cancel</button>
          <button
            className={danger ? "button danger" : "button"}
            disabled={!canConfirm}
            onClick={() => void onConfirm()}
            type="button"
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      )}
    >
      {requiresTypedConfirmation ? (
        <label>
          <span>Type {confirmationText} to continue</span>
          <input
            autoComplete="off"
            autoFocus
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder={confirmationText}
            spellCheck={false}
          />
        </label>
      ) : null}
    </AppModal>
  );
}
