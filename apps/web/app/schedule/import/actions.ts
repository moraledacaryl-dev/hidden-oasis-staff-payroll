"use server";

import { apiBaseUrl } from "@/lib/backend";
import { backendHeaders } from "@/lib/backend";

export type AttendanceTemplateRow = Record<string, string>;

export async function importAttendanceTemplate(
  rows: AttendanceTemplateRow[],
  dryRun: boolean,
  fileName?: string,
) {
  const response = await fetch(`${apiBaseUrl()}/api/v1/attendance/template-import`, {
    method: "POST",
    headers: await backendHeaders(true),
    body: JSON.stringify({ rows, dry_run: dryRun, file_name: fileName || "attendance-upload-template.csv" }),
    cache: "no-store",
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    return { ok: false, message: data.detail || data.message || "Attendance template upload failed." };
  }
  return data;
}
