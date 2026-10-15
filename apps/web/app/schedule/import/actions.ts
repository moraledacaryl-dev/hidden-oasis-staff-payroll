"use server";

import { apiBaseUrl } from "@/lib/backend";
import { backendHeaders } from "@/lib/backend";

export type AttendanceTemplateRow = Record<string, string>;

type ApiErrorDetail = {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
  input?: unknown;
};

function formatApiError(value: unknown): string {
  if (typeof value === "string") return value;

  if (Array.isArray(value)) {
    const messages = value
      .map((item) => formatApiError(item))
      .filter(Boolean);
    return messages.join("; ");
  }

  if (value && typeof value === "object") {
    const detail = value as ApiErrorDetail;
    const location = Array.isArray(detail.loc)
      ? detail.loc.filter((part) => part !== "body").join(" → ")
      : "";
    const message = typeof detail.msg === "string" ? detail.msg : "";

    if (location && message) return `${location}: ${message}`;
    if (message) return message;

    try {
      return JSON.stringify(value);
    } catch {
      return "Attendance template upload failed.";
    }
  }

  return value == null ? "Attendance template upload failed." : String(value);
}

export async function importAttendanceTemplate(
  rows: AttendanceTemplateRow[],
  dryRun: boolean,
  fileName?: string,
) {
  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/attendance/template-import-v2`, {
      method: "POST",
      headers: await backendHeaders(true),
      body: JSON.stringify({ rows, dry_run: dryRun, file_name: fileName || "attendance-upload-template.csv" }),
      cache: "no-store",
    });

    const raw = await response.text();
    let data: Record<string, unknown> = {};
    if (raw) {
      try {
        data = JSON.parse(raw) as Record<string, unknown>;
      } catch {
        data = {};
      }
    }

    if (!response.ok) {
      const detail = data.detail ?? data.message;
      const fallback = raw && raw.length <= 500 && !raw.trimStart().startsWith("<")
        ? raw
        : `Attendance API returned HTTP ${response.status}.`;
      return {
        ok: false,
        message: detail ? formatApiError(detail) : fallback,
      };
    }
    return data;
  } catch (error) {
    const reason = error instanceof Error && error.message ? `: ${error.message}` : ".";
    return {
      ok: false,
      message: `Could not reach the attendance API${reason}`,
    };
  }
}
