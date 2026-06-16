export function StatusBadge({ label, tone = "ok" }: { label: string; tone?: "ok" | "warning" | "danger" }) {
  return <span className={`badge ${tone}`}>{label}</span>;
}

export function severityTone(severity: string): "ok" | "warning" | "danger" {
  if (severity.toLowerCase().includes("block")) return "danger";
  if (severity.toLowerCase().includes("warn")) return "warning";
  return "ok";
}
