from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "payroll" / "runs" / "[id]" / "page.tsx"
ROUTE = ROOT / "apps" / "web" / "app" / "api" / "payroll" / "workflow" / "route.ts"

ROUTE_B64 = "aW1wb3J0IHsgY29va2llcyB9IGZyb20gIm5leHQvaGVhZGVycyI7CmltcG9ydCB7IHJldmFsaWRhdGVQYXRoIH0gZnJvbSAibmV4dC9jYWNoZSI7CmltcG9ydCB7IE5leHRSZXNwb25zZSB9IGZyb20gIm5leHQvc2VydmVyIjsKaW1wb3J0IHsgQUNDRVNTX1RPS0VOX0NPT0tJRSB9IGZyb20gIkAvbGliL3Nlc3Npb24tY2xpZW50IjsKCmZ1bmN0aW9uIGFwaUJhc2VVcmwoKTogc3RyaW5nIHsKICByZXR1cm4gKHByb2Nlc3MuZW52LlNUQUZGX1BBWVJPTExfQVBJX1VSTCB8fCBwcm9jZXNzLmVudi5ORVhUX1BVQkxJQ19TVEFGRl9QQVlST0xMX0FQSV9VUkwgfHwgImh0dHA6Ly8xMjcuMC4wLjE6ODAwMSIpLnJlcGxhY2UoL1wvJC8sICIiKTsKfQoKZXhwb3J0IGFzeW5jIGZ1bmN0aW9uIFBPU1QocmVxdWVzdDogUmVxdWVzdCkgewogIGNvbnN0IHRva2VuID0gKGF3YWl0IGNvb2tpZXMoKSkuZ2V0KEFDQ0VTU19UT0tFTl9DT09LSUUpPy52YWx1ZTsKICBpZiAoIXRva2VuKSByZXR1cm4gTmV4dFJlc3BvbnNlLmpzb24oeyBvazogZmFsc2UsIG1lc3NhZ2U6ICJOb3Qgc2lnbmVkIGluLiIgfSwgeyBzdGF0dXM6IDQwMSB9KTsKCiAgY29uc3QgYm9keSA9IGF3YWl0IHJlcXVlc3QuanNvbigpOwogIGNvbnN0IHJ1bklkID0gTnVtYmVyKGJvZHkucnVuX2lkIHx8IDApOwogIGNvbnN0IGFjdGlvbiA9IFN0cmluZyhib2R5LmFjdGlvbiB8fCAiIik7CiAgY29uc3QgZW5kcG9pbnQgPSBhY3Rpb24gPT09ICJzdWJtaXQtcmV2aWV3IiA/ICJsb2NrIiA6IGFjdGlvbiA9PT0gImFwcHJvdmUiID8gImFwcHJvdmUiIDogIiI7CgogIGlmICghcnVuSWQgfHwgIWVuZHBvaW50KSB7CiAgICByZXR1cm4gTmV4dFJlc3BvbnNlLmpzb24oeyBvazogZmFsc2UsIG1lc3NhZ2U6ICJJbnZhbGlkIHBheXJvbGwgd29ya2Zsb3cgcmVxdWVzdC4iIH0sIHsgc3RhdHVzOiA0MjIgfSk7CiAgfQoKICBjb25zdCByZXNwb25zZSA9IGF3YWl0IGZldGNoKGAke2FwaUJhc2VVcmwoKX0vYXBpL3YxL3BheXJvbGwvcnVucy8ke3J1bklkfS8ke2VuZHBvaW50fWAsIHsKICAgIG1ldGhvZDogIlBPU1QiLAogICAgaGVhZGVyczogewogICAgICBBdXRob3JpemF0aW9uOiBgQmVhcmVyICR7dG9rZW59YCwKICAgICAgIkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIiwKICAgICAgLi4uKHByb2Nlc3MuZW52LlNUQUZGX1BBWVJPTExfQVBJX0tFWSA/IHsgIlgtQVBJLUtleSI6IHByb2Nlc3MuZW52LlNUQUZGX1BBWVJPTExfQVBJX0tFWSB9IDoge30pLAogICAgfSwKICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHt9KSwKICAgIGNhY2hlOiAibm8tc3RvcmUiLAogIH0pOwoKICBjb25zdCBkYXRhID0gYXdhaXQgcmVzcG9uc2UuanNvbigpLmNhdGNoKCgpID0+ICh7fSkpOwogIGlmIChyZXNwb25zZS5vaykgewogICAgcmV2YWxpZGF0ZVBhdGgoYC9wYXlyb2xsL3J1bnMvJHtydW5JZH1gKTsKICAgIHJldmFsaWRhdGVQYXRoKCIvcGF5cm9sbC9ydW5zIik7CiAgICByZXZhbGlkYXRlUGF0aChgL3BheXJvbGwvcnVucy8ke3J1bklkfS9wYXlzbGlwc2ApOwogICAgcmV2YWxpZGF0ZVBhdGgoYC9wYXlyb2xsL3J1bnMvJHtydW5JZH0vYXVkaXRgKTsKICB9CiAgcmV0dXJuIE5leHRSZXNwb25zZS5qc29uKGRhdGEsIHsgc3RhdHVzOiByZXNwb25zZS5zdGF0dXMgfSk7Cn0K"

ROUTE.parent.mkdir(parents=True, exist_ok=True)
ROUTE.write_bytes(base64.b64decode(ROUTE_B64))

text = PAGE.read_text(encoding="utf-8")

import_anchor = 'import { MarkPaidButton } from "@/components/MarkPaidButton";'
workflow_import = 'import { PayrollWorkflowButton } from "@/components/PayrollWorkflowButton";'
if workflow_import not in text:
    text = text.replace(import_anchor, import_anchor + "\n" + workflow_import)

button_anchor = '              {canRecalculate ? <RecalculatePayrollButton runId={run.id} /> : null}'
button_block = button_anchor + '\n              {run.status === "Draft" ? <PayrollWorkflowButton runId={run.id} action="submit-review" /> : null}\n              {session.role_key === "owner" && run.status === "For Owner Review" ? <PayrollWorkflowButton runId={run.id} action="approve" /> : null}'
if 'action="submit-review"' not in text:
    text = text.replace(button_anchor, button_block)

hint_anchor = '            {canRecalculate ? <p className="muted">Use Recalculate Draft after changing Schedule, Attendance, OT, Leave, employee payroll settings, or cash advances. Manual employee adjustments are preserved.</p> : null}'
hint_block = hint_anchor + '\n            {run.status === "Draft" ? <p className="muted">When the figures are final, submit the run for owner review.</p> : null}\n            {session.role_key === "owner" && run.status === "For Owner Review" ? <p className="muted">Review the final totals and payslips, then approve the payroll.</p> : null}'
if 'When the figures are final' not in text:
    text = text.replace(hint_anchor, hint_block)

PAGE.write_text(text, encoding="utf-8")
print("Payroll workflow controls activated.")
