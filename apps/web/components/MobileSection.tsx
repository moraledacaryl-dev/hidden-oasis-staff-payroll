"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

/** Secondary content stays expanded on desktop and is explicitly opened on phones. */
export function MobileSection({ title, description, children, id, className = "" }: {
  title: string; description?: string; children: ReactNode; id?: string; className?: string;
}) {
  const contentId = useId();
  const root = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let frame = 0;
    const revealAnchor = (hash = window.location.hash) => {
      let target: HTMLElement | null = null;
      try { target = document.getElementById(decodeURIComponent(hash.slice(1))); } catch { return; }
      if (target && root.current?.contains(target)) {
        setExpanded(true);
        frame = requestAnimationFrame(() => target?.scrollIntoView({ block: "start" }));
      }
    };
    const onHashChange = () => revealAnchor();
    const onAnchorClick = (event: MouseEvent) => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest("a") : null;
      if (!anchor || anchor.target === "_blank") return;
      const url = new URL(anchor.href, window.location.href);
      if (url.origin === window.location.origin && url.pathname === window.location.pathname && url.hash) revealAnchor(url.hash);
    };
    revealAnchor();
    window.addEventListener("hashchange", onHashChange);
    document.addEventListener("click", onAnchorClick);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("hashchange", onHashChange); document.removeEventListener("click", onAnchorClick); };
  }, []);

  return <div ref={root} id={id} className={`mobile-section ${className}`} data-expanded={expanded}>
    <button className="mobile-section-toggle" type="button" aria-expanded={expanded} aria-controls={contentId} onClick={() => setExpanded(!expanded)}>
      <span><strong>{title}</strong>{description ? <small>{description}</small> : null}</span>
      <span className="mobile-section-chevron" aria-hidden="true">⌄</span>
    </button>
    <div id={contentId} className="mobile-section-content">{children}</div>
  </div>;
}
