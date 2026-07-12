"use client";

import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

type SurfaceProps = {
  open: boolean;
  eyebrow?: string;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  closeLabel?: string;
};

function useSurfaceLifecycle(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);
}

function SurfaceHeader({ eyebrow, title, description, onClose, closeLabel = "Close" }: Pick<SurfaceProps, "eyebrow" | "title" | "description" | "onClose" | "closeLabel">) {
  return (
    <header className="app-surface-header">
      <div className="app-surface-heading">
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      <button aria-label={closeLabel} className="app-surface-close" onClick={onClose} type="button"><X aria-hidden="true" size={18} /></button>
    </header>
  );
}

export function AppDrawer({ open, eyebrow, title, description, children, footer, onClose, closeLabel }: SurfaceProps) {
  useSurfaceLifecycle(open, onClose);
  if (!open) return null;
  return (
    <div className="app-surface-backdrop app-drawer-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }} role="presentation">
      <section aria-modal="true" className="app-surface app-drawer" role="dialog">
        <SurfaceHeader closeLabel={closeLabel} description={description} eyebrow={eyebrow} onClose={onClose} title={title} />
        <div className="app-surface-body">{children}</div>
        {footer ? <footer className="app-surface-footer">{footer}</footer> : null}
      </section>
    </div>
  );
}

export function AppModal({ open, eyebrow, title, description, children, footer, onClose, closeLabel }: SurfaceProps) {
  useSurfaceLifecycle(open, onClose);
  if (!open) return null;
  return (
    <div className="app-surface-backdrop app-modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }} role="presentation">
      <section aria-modal="true" className="app-surface app-modal" role="dialog">
        <SurfaceHeader closeLabel={closeLabel} description={description} eyebrow={eyebrow} onClose={onClose} title={title} />
        <div className="app-surface-body">{children}</div>
        {footer ? <footer className="app-surface-footer">{footer}</footer> : null}
      </section>
    </div>
  );
}

export function SurfaceContext({ children }: { children: ReactNode }) {
  return <div className="app-surface-context">{children}</div>;
}

export function SurfaceSection({ number, title, description, children }: { number?: number | string; title: string; description?: string; children: ReactNode }) {
  return (
    <section className="app-surface-section">
      <header className="app-surface-section-header">
        {number !== undefined ? <span>{number}</span> : null}
        <div><h3>{title}</h3>{description ? <p>{description}</p> : null}</div>
      </header>
      <div className="app-surface-section-body">{children}</div>
    </section>
  );
}
