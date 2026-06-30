"use client";

import { useMemo, useState, useTransition } from "react";
import { importAttendanceTemplate, type AttendanceTemplateRow } from "@/app/schedule/import/actions";

const REQUIRED_COLUMNS = [
  "work_date",
  "employee_name",
  "biometric_id",
  "time_in",
  "time_out",
  "time_out_date",
  "break_minutes",
  "attendance_status",
  "remarks",
  "is_absent",
  "is_halfday",
  "is_ot",
  "ot_hours",
  "ot_reason",
  "needs_review",
  "review_note",
];

type ImportResult = {
  ok?: boolean;
  message?: string;
  dry_run?: boolean;
  summary?: {
    rows: number;
    ready: number;
    needs_review: number;
    errors: number;
    imported: number;
  };
  items?: Array<{
    row_number: number;
    employee_name: string;
    work_date: string;
    actual_in: string | null;
    actual_out: string | null;
    attendance_status: string;
    needs_review: number;
    issues: string[];
  }>;
};

function parseCsvLine(line: string) {
  const cells: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === '"' && quoted && next === '"') {
      current += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      cells.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
}

function parseCsv(text: string): { rows: AttendanceTemplateRow[]; columns: string[] } {
  const lines = text
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return { rows: [], columns: [] };
  const columns = parseCsvLine(lines[0]).map((column) => column.trim());
  const rows = lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    return columns.reduce<AttendanceTemplateRow>((acc, column, index) => {
      acc[column] = cells[index] || "";
      return acc;
    }, {});
  });
  return { rows, columns };
}

export function AttendanceTemplateUploadClient() {
  const [rows, setRows] = useState<AttendanceTemplateRow[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [fileName, setFileName] = useState("");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [isPending, startTransition] = useTransition();

  const missingColumns = useMemo(
    () => REQUIRED_COLUMNS.filter((column) => !columns.includes(column)),
    [columns],
  );

  async function handleFile(file: File | null) {
    setMessage("");
    setResult(null);
    setRows([]);
    setColumns([]);
    if (!file) return;
    const text = await file.text();
    const parsed = parseCsv(text);
    setRows(parsed.rows);
    setColumns(parsed.columns);
    setFileName(file.name);
    if (!parsed.rows.length) setMessage("No rows were found in the CSV.");
  }

  function submit(dryRun: boolean) {
    if (!rows.length) {
      setMessage("Choose a completed CSV template first.");
      return;
    }
    if (missingColumns.length) {
      setMessage(`Missing required columns: ${missingColumns.join(", ")}`);
      return;
    }
    setMessage("");
    startTransition(async () => {
      const response = await importAttendanceTemplate(rows, dryRun, fileName);
      setResult(response);
      if (!response?.ok) {
        setMessage(response?.message || "Attendance template upload failed.");
        return;
      }
      setMessage(dryRun ? "Preview complete. Review flagged rows before importing." : "Attendance rows imported.");
    });
  }

  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="card">
        <div className="panel-title">
          <div>
            <span className="eyebrow">Template</span>
            <h2>Download and complete the CSV</h2>
          </div>
          <a className="primary-link" href="/templates/attendance-upload-template.csv" download>
            Download template
          </a>
        </div>
        <p className="muted">
          Use one row per employee per work date. For overnight shifts, set time_out_date to the next day.
          Keep biometric raw files separately; this upload is the clean payroll-ready template.
        </p>
      </section>

      <section className="card">
        <div className="panel-title">
          <div>
            <span className="eyebrow">Upload</span>
            <h2>Import completed template</h2>
          </div>
        </div>
        <div className="grid" style={{ gap: 10 }}>
          <input type="file" accept=".csv,text/csv" onChange={(event) => void handleFile(event.target.files?.[0] || null)} />
          {fileName ? <p className="muted">Selected: {fileName} · {rows.length} rows</p> : null}
          {missingColumns.length && columns.length ? (
            <p className="error-text">Missing columns: {missingColumns.join(", ")}</p>
          ) : null}
          <div className="badge-row">
            <button className="primary-link" disabled={isPending || !rows.length || Boolean(missingColumns.length)} onClick={() => submit(true)} type="button">
              Preview / Validate
            </button>
            <button className="primary-link" disabled={isPending || !result?.summary || Boolean(result.summary.errors)} onClick={() => submit(false)} type="button">
              Import to attendance
            </button>
          </div>
          {message ? <p className={message.includes("failed") || message.includes("Missing") ? "error-text" : "muted"}>{message}</p> : null}
        </div>
      </section>

      {result?.summary ? (
        <section className="card">
          <div className="panel-title">
            <div>
              <span className="eyebrow">Import preview</span>
              <h2>{result.dry_run ? "Review before import" : "Imported"}</h2>
            </div>
          </div>
          <div className="grid cols-4">
            <div className="metric"><span className="eyebrow">Rows</span><strong className="metric-value">{result.summary.rows}</strong></div>
            <div className="metric"><span className="eyebrow">Ready</span><strong className="metric-value">{result.summary.ready}</strong></div>
            <div className="metric"><span className="eyebrow">Review</span><strong className="metric-value">{result.summary.needs_review}</strong></div>
            <div className="metric"><span className="eyebrow">Errors</span><strong className="metric-value">{result.summary.errors}</strong></div>
          </div>
          <div className="table-wrap" style={{ marginTop: 16 }}>
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Employee</th>
                  <th>Date</th>
                  <th>In / Out</th>
                  <th>Status</th>
                  <th>Flags</th>
                </tr>
              </thead>
              <tbody>
                {(result.items || []).slice(0, 50).map((item) => (
                  <tr key={item.row_number}>
                    <td>{item.row_number}</td>
                    <td>{item.employee_name || "—"}</td>
                    <td>{item.work_date || "—"}</td>
                    <td>{item.actual_in || "—"}–{item.actual_out || "—"}</td>
                    <td>{item.attendance_status}</td>
                    <td>{item.issues.length ? item.issues.join("; ") : item.needs_review ? "Needs review" : "Ready"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(result.items || []).length > 50 ? <p className="muted">Showing first 50 rows only.</p> : null}
        </section>
      ) : null}
    </div>
  );
}
