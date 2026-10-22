/**
 * Encode a CSV cell for spreadsheet programs.
 *
 * Excel/LibreOffice can execute formula-like fields even inside CSV quotes.
 * Prepending a literal apostrophe to untrusted text prevents interpretation
 * as =, +, -, @ formulas (including whitespace/control-prefix variants).
 * Numeric values remain numeric. Escaping of commas, quotes and CR/LF still
 * follows RFC 4180-compatible quoting.
 */
export function csvCell(value) {
  if (value === null || value === undefined) return "";
  const raw = String(value);
  const untrustedText = typeof value === "string";
  const formulaPrefix = /^[\s\u200b\ufeff\u0000-\u001f\u007f]*[=+\-@]/u;
  const leadingControl = /^[\t\r\n\u0000-\u001f\u007f]/u;
  const neutralized = untrustedText && (formulaPrefix.test(raw) || leadingControl.test(raw))
    ? "'" + raw
    : raw;
  return /[",\r\n]/.test(neutralized)
    ? '"' + neutralized.replaceAll('"', '""') + '"'
    : neutralized;
}

export function csvDocument(headers, rows) {
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
