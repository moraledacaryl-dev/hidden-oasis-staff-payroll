import type { ReactNode } from "react";
import styles from "./UiPrimitives.module.css";

export function PageHeading({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className={styles.pageHeading}>
      <div className={styles.pageHeadingCopy}>
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className={styles.pageActions}>{actions}</div> : null}
    </header>
  );
}

export function MetricGrid({ children }: { children: ReactNode }) {
  return <section className={styles.metricGrid}>{children}</section>;
}

export function MetricCard({ value, label }: { value: ReactNode; label: ReactNode }) {
  return (
    <div className={styles.metricCard}>
      <strong className={styles.metricValue}>{value}</strong>
      <span className={styles.metricLabel}>{label}</span>
    </div>
  );
}

export function SectionCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`${styles.sectionCard} ${className}`}>{children}</section>;
}

export function SectionHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className={styles.sectionHeader}>
      <div className={styles.sectionHeaderCopy}>
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className={styles.sectionActions}>{actions}</div> : null}
    </header>
  );
}

export function SectionBody({ children, flush = false }: { children: ReactNode; flush?: boolean }) {
  return <div className={flush ? styles.sectionBodyFlush : styles.sectionBody}>{children}</div>;
}

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className={styles.toolbar}>{children}</div>;
}

export function ToolbarGroup({ children }: { children: ReactNode }) {
  return <div className={styles.toolbarGroup}>{children}</div>;
}

export function Notice({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "ok" | "warning" | "danger" }) {
  const toneClass = tone === "ok" ? styles.noticeOk : tone === "warning" ? styles.noticeWarning : tone === "danger" ? styles.noticeDanger : "";
  return <div className={`${styles.notice} ${toneClass}`}>{children}</div>;
}

export function DrawerFooter({ start, end }: { start?: ReactNode; end?: ReactNode }) {
  return (
    <footer className={styles.drawerFooter}>
      <div className={styles.drawerFooterStart}>{start}</div>
      <div className={styles.drawerFooterEnd}>{end}</div>
    </footer>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className={styles.emptyState}>
      <strong>{title}</strong>
      {description ? <span>{description}</span> : null}
      {action}
    </div>
  );
}
