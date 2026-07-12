"use client";

import { useMemo, useState, useTransition } from "react";
import { CheckCircle2, Download, FileSpreadsheet, ShieldCheck, UploadCloud } from "lucide-react";
import { importAttendanceTemplate, type AttendanceTemplateRow } from "@/app/schedule/import/actions";
import { StatusBadge } from "@/components/StatusBadge";

const REQUIRED_COLUMNS = [
  "work_date", "employee_name", "biometric_id", "time_in", "time_out", "time_out_date", "break_minutes",
  "attendance_status", "remarks", "is_absent", "is_halfday", "is_ot", "ot_hours", "ot_reason",
  "needs_review", "review_note",
];

type ImportResult = {
  ok?: boolean;
  message?: string;
  dry_run?: boolean;
  summary?: { rows: number; ready: number; needs_review: number; errors: number; imported: number };
  items?: Array<{ row_number: number; employee_name: string; work_date: string; actual_in: string | null; actual_out: string | null; attendance_status: string; needs_review: number; issues: string[] }>;
};

function parseCsvLine(line: string) {
  const cells: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === '"' && quoted && next === '"') { current += '"'; index += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === "," && !quoted) { cells.push(current.trim()); current = ""; }
    else current += char;
  }
  cells.push(current.trim());
  return cells;
}

function parseCsv(text: string): { rows: AttendanceTemplateRow[]; columns: string[] } {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return { rows: [], columns: [] };
  const columns = parseCsvLine(lines[0]).map((column) => column.trim());
  const rows = lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    return columns.reduce<AttendanceTemplateRow>((acc, column, index) => { acc[column] = cells[index] || ""; return acc; }, {});
  });
  return { rows, columns };
}

function normalizeTemplateDays(value: string) {
  const parsed = Number(value || 16);
  if (!Number.isFinite(parsed)) return "16";
  return String(Math.min(31, Math.max(1, Math.trunc(parsed))));
}

export function AttendanceTemplateUploadClient() {
  const [rows, setRows] = useState<AttendanceTemplateRow[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [fileName, setFileName] = useState("");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [templateStart, setTemplateStart] = useState("");
  const [templateDays, setTemplateDays] = useState("16");
  const [isPending, startTransition] = useTransition();

  const templateHref = useMemo(() => {
    const params = new URLSearchParams();
    if (templateStart) params.set("start", templateStart);
    params.set("days", normalizeTemplateDays(templateDays));
    return `/api/attendance-template/download?${params.toString()}`;
  }, [templateStart, templateDays]);
  const missingColumns = useMemo(() => REQUIRED_COLUMNS.filter((column) => !columns.includes(column)), [columns]);

  async function handleFile(file: File | null) {
    setMessage(""); setResult(null); setRows([]); setColumns([]);
    if (!file) return;
    const parsed = parseCsv(await file.text());
    setRows(parsed.rows); setColumns(parsed.columns); setFileName(file.name);
    if (!parsed.rows.length) setMessage("No rows were found in the CSV.");
  }

  function submit(dryRun: boolean) {
    if (!rows.length) { setMessage("Choose a completed CSV template first."); return; }
    if (missingColumns.length) { setMessage(`Missing required columns: ${missingColumns.join(", ")}`); return; }
    setMessage("");
    startTransition(async () => {
      const response = await importAttendanceTemplate(rows, dryRun, fileName);
      setResult(response);
      if (!response?.ok) { setMessage(response?.message || "Attendance template upload failed."); return; }
      setMessage(dryRun ? "Preview complete. Review flagged rows before importing." : "Attendance rows imported.");
    });
  }

  const summary = result?.summary || { rows: rows.length, ready: 0, needs_review: 0, errors: 0, imported: 0 };

  return (
    <div className="import-shell">
      <section className="import-kpis">
        <div className="import-kpi"><span>Rows selected</span><strong>{summary.rows}</strong></div>
        <div className="import-kpi"><span>Ready</span><strong>{summary.ready}</strong></div>
        <div className="import-kpi"><span>Needs review</span><strong>{summary.needs_review}</strong></div>
        <div className="import-kpi"><span>Errors</span><strong>{summary.errors}</strong></div>
      </section>

      <section className="import-stage">
        <div className="import-upload-card">
          <header className="import-card-head"><div><span className="eyebrow">Safe import</span><h2>Upload completed attendance template</h2><p>Validate every row before anything is written to attendance.</p></div><StatusBadge label="Preview required" tone="ok" /></header>
          <div className="import-card-body">
            <label className="import-dropzone">
              <UploadCloud size={28} />
              <strong>{fileName || "Choose a CSV attendance file"}</strong>
              <span>{fileName ? `${rows.length} rows detected` : "Only the Hidden Oasis attendance template is accepted."}</span>
              <input type="file" accept=".csv,text/csv" onChange={(event) => void handleFile(event.target.files?.[0] || null)} />
            </label>
            {missingColumns.length && columns.length ? <div className="import-message error">Missing columns: {missingColumns.join(", ")}</div> : null}
            {message ? <div className={`import-message ${message.includes("failed") || message.includes("Missing") ? "error" : ""}`}>{message}</div> : null}
            <div className="import-actions">
              <button className="button secondary" disabled={isPending || !rows.length || Boolean(missingColumns.length)} onClick={() => submit(true)} type="button"><ShieldCheck size={15} />Preview / Validate</button>
              <button className="button" disabled={isPending || !result?.summary || Boolean(result.summary.errors) || !result.dry_run} onClick={() => submit(false)} type="button"><CheckCircle2 size={15} />Import to attendance</button>
            </div>
          </div>
        </div>

        <aside className="import-side-card">
          <header className="import-card-head"><div><span className="eyebrow">Template</span><h2>Prepare employee grid</h2><p>Download a clean date range before entering logs.</p></div><FileSpreadsheet size={20} /></header>
          <div className="import-card-body">
            <div className="import-template-form">
              <label>Start date<input type="date" value={templateStart} onChange={(event) => setTemplateStart(event.target.value)} /></label>
              <label>Days<input inputMode="numeric" min="1" max="31" type="number" value={templateDays} onBlur={() => setTemplateDays((value) => normalizeTemplateDays(value))} onChange={(event) => setTemplateDays(event.target.value)} /></label>
            </div>
            <a className="button secondary" href={templateHref} download style={{ marginTop: 12 }}><Download size={15} />Download grid template</a>
            <div className="import-side-list" style={{ marginTop: 14 }}>
              <div><strong>Required structure</strong><span>{REQUIRED_COLUMNS.length} named columns must remain unchanged.</span></div>
              <div><strong>Overnight records</strong><span>Use time_out_date when a shift ends after midnight.</span></div>
              <div><strong>Review protection</strong><span>Flagged and invalid rows remain visible before commit.</span></div>
            </div>
          </div>
        </aside>
      </section>

      {result?.summary ? <section className="import-preview-card">
        <header className="import-card-head"><div><span className="eyebrow">Import preview</span><h2>{result.dry_run ? "Review before import" : "Import complete"}</h2><p>{fileName} · showing validation results from the current file.</p></div><StatusBadge label={result.summary.errors ? "Errors found" : result.dry_run ? "Ready to commit" : "Imported"} tone={result.summary.errors ? "danger" : "ok"} /></header>
        <div className="import-preview-summary"><div><span>Rows</span><strong>{result.summary.rows}</strong></div><div><span>Ready</span><strong>{result.summary.ready}</strong></div><div><span>Review</span><strong>{result.summary.needs_review}</strong></div><div><span>Errors</span><strong>{result.summary.errors}</strong></div></div>
        <div className="table-wrap"><table><thead><tr><th>Row</th><th>Employee</th><th>Date</th><th>In / Out</th><th>Status</th><th>Validation</th></tr></thead><tbody>{(result.items || []).slice(0, 50).map((item) => <tr key={item.row_number}><td>{item.row_number}</td><td><strong>{item.employee_name || "—"}</strong></td><td>{item.work_date || "—"}</td><td>{item.actual_in || "—"}–{item.actual_out || "—"}</td><td>{item.attendance_status}</td><td>{item.issues.length ? item.issues.join("; ") : item.needs_review ? "Needs review" : "Ready"}</td></tr>)}</tbody></table></div>
        {(result.items || []).length > 50 ? <p className="muted" style={{ padding: "0 18px 16px" }}>Showing first 50 rows only.</p> : null}
      </section> : null}
    </div>
  );
}
