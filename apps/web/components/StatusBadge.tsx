export type StatusTone = "neutral" | "info" | "ok" | "warning" | "danger";

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: StatusTone }) {
  const mappedTone = tone === "info" ? "info" : tone;
  return <span className={`badge ${mappedTone}`}>{label}</span>;
}

export function severityTone(severity: string): StatusTone {
  const normalized = severity.toLowerCase();
  if (normalized.includes("block") || normalized.includes("critical") || normalized.includes("error")) return "danger";
  if (normalized.includes("warn") || normalized.includes("pending") || normalized.includes("review")) return "warning";
  if (normalized.includes("info") || normalized.includes("draft")) return "info";
  if (normalized.includes("ok") || normalized.includes("ready") || normalized.includes("approved") || normalized.includes("paid")) return "ok";
  return "neutral";
}
