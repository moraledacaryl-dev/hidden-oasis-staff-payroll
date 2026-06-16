export function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string;
}) {
  return (
    <section className="card metric">
      <span className="muted">{label}</span>
      <strong className="metric-value">{value}</strong>
      {detail ? <span className="muted">{detail}</span> : null}
    </section>
  );
}
