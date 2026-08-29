"use client";

import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
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

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function useSurfaceLifecycle(open: boolean, onClose: () => void, surfaceRef: RefObject<HTMLElement | null>) {
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!open) return;

    const html = document.documentElement;
    const body = document.body;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousHtmlOverflow = html.style.overflow;
    const previousHtmlOverflowX = html.style.overflowX;
    const previousBodyOverflow = body.style.overflow;
    const previousBodyOverflowX = body.style.overflowX;
    const previousBodyOverscroll = body.style.overscrollBehavior;

    html.dataset.appSurfaceOpen = "true";
    html.style.overflow = "hidden";
    html.style.overflowX = "hidden";
    body.style.overflow = "hidden";
    body.style.overflowX = "hidden";
    body.style.overscrollBehavior = "none";

    const focusFrame = window.requestAnimationFrame(() => {
      const surface = surfaceRef.current;
      if (!surface) return;
      const autofocus = surface.querySelector<HTMLElement>("[autofocus]");
      const firstFocusable = surface.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      (autofocus || firstFocusable || surface).focus();
    });

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }

      if (event.key !== "Tab") return;
      const surface = surfaceRef.current;
      if (!surface) return;
      const focusable = Array.from(surface.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
        .filter((element) => !element.hasAttribute("disabled") && element.getAttribute("aria-hidden") !== "true");

      if (!focusable.length) {
        event.preventDefault();
        surface.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      delete html.dataset.appSurfaceOpen;
      html.style.overflow = previousHtmlOverflow;
      html.style.overflowX = previousHtmlOverflowX;
      body.style.overflow = previousBodyOverflow;
      body.style.overflowX = previousBodyOverflowX;
      body.style.overscrollBehavior = previousBodyOverscroll;
      document.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, [open, surfaceRef]);
}

function SurfaceHeader({ eyebrow, title, description, onClose, closeLabel = "Close", titleId, descriptionId }: Pick<SurfaceProps, "eyebrow" | "title" | "description" | "onClose" | "closeLabel"> & { titleId: string; descriptionId: string }) {
  return (
    <header className="app-surface-header">
      <div className="app-surface-heading">
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h2 id={titleId}>{title}</h2>
        {description ? <p id={descriptionId}>{description}</p> : null}
      </div>
      <button aria-label={closeLabel} className="app-surface-close" onClick={onClose} type="button"><X aria-hidden="true" size={18} /></button>
    </header>
  );
}

export function AppDrawer({ open, eyebrow, title, description, children, footer, onClose, closeLabel }: SurfaceProps) {
  const surfaceRef = useRef<HTMLElement | null>(null);
  const id = useId();
  const titleId = `${id}-title`;
  const descriptionId = `${id}-description`;
  useSurfaceLifecycle(open, onClose, surfaceRef);
  if (!open) return null;
  return (
    <div className="app-surface-backdrop app-drawer-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }} role="presentation">
      <section aria-describedby={description ? descriptionId : undefined} aria-labelledby={titleId} aria-modal="true" className="app-surface app-drawer" ref={surfaceRef} role="dialog" tabIndex={-1}>
        <SurfaceHeader closeLabel={closeLabel} description={description} descriptionId={descriptionId} eyebrow={eyebrow} onClose={onClose} title={title} titleId={titleId} />
        <div className="app-surface-body">{children}</div>
        {footer ? <footer className="app-surface-footer">{footer}</footer> : null}
      </section>
    </div>
  );
}

export function AppModal({ open, eyebrow, title, description, children, footer, onClose, closeLabel }: SurfaceProps) {
  const surfaceRef = useRef<HTMLElement | null>(null);
  const id = useId();
  const titleId = `${id}-title`;
  const descriptionId = `${id}-description`;
  useSurfaceLifecycle(open, onClose, surfaceRef);
  if (!open) return null;
  return (
    <div className="app-surface-backdrop app-modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }} role="presentation">
      <section aria-describedby={description ? descriptionId : undefined} aria-labelledby={titleId} aria-modal="true" className="app-surface app-modal" ref={surfaceRef} role="dialog" tabIndex={-1}>
        <SurfaceHeader closeLabel={closeLabel} description={description} descriptionId={descriptionId} eyebrow={eyebrow} onClose={onClose} title={title} titleId={titleId} />
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
