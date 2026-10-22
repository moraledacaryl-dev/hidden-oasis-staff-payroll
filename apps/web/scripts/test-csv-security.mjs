import assert from "node:assert/strict";
import test from "node:test";
import { csvCell, csvDocument } from "../lib/csv-security.mjs";

test("formula characters are neutralized as text, not spreadsheet commands", () => {
  for (const attack of [
    "=1+2",
    "+SUM(1,2)",
    "-4+5",
    "@SUM(1,2)",
    "  =HYPERLINK(\"https://example.test\",\"click\")",
    "\t=1+2",
    "\r=1+2",
    "\n=1+2",
    "\uFEFF=1+2",
    "\u200b@cmd",
  ]) {
    const encoded = csvCell(attack);
    assert.ok(encoded.replace(/^"/, "").startsWith("'"), attack);
    assert.ok(!encoded.startsWith("="), attack);
  }
});

test("ordinary text and numeric payroll values are preserved", () => {
  assert.equal(csvCell("Ana Santos"), "Ana Santos");
  assert.equal(csvCell(""), "");
  assert.equal(csvCell(null), "");
  assert.equal(csvCell(1250.25), "1250.25");
  assert.equal(csvCell(-200), "-200");
  assert.equal(csvCell("00123"), "00123");
});

test("quotes, commas, newlines, and CR are escaped", () => {
  assert.equal(csvCell('Ana, "Joy"'), '"Ana, ""Joy"""');
  assert.equal(csvCell("a\nb"), '"a\nb"');
  assert.equal(csvCell("a\rb"), '"a\rb"');
  assert.equal(csvCell('=HYPERLINK("x","y")'), '"\'=HYPERLINK(""x"",""y"")"');
});

test("complete exported rows guard untrusted notes and retain the header", () => {
  assert.equal(
    csvDocument(["employee", "net_pay", "notes"], [["Ana", 900, "=1+1"]]),
    "employee,net_pay,notes\r\nAna,900,'=1+1\r\n",
  );
});
