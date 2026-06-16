"use client";

export function PrintButton({ label = "Print" }: { label?: string }) {
  return (
    <button className="primary-button" type="button" onClick={() => window.print()}>
      {label}
    </button>
  );
}
