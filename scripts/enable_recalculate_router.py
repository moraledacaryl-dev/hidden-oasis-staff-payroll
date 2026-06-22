from pathlib import Path

path = Path(__file__).resolve().parents[1] / "api" / "server_review.py"
text = path.read_text()

imp = "from api.payroll_recalculate import router as payroll_recalculate_router"
inc = "app.include_router(payroll_recalculate_router)"

if imp not in text:
    text = text.replace(
        "from api.payroll_adjustments_v3 import router as payroll_adjustments_router",
        "from api.payroll_adjustments_v3 import router as payroll_adjustments_router\n" + imp,
    )

if inc not in text:
    text = text.replace(
        "app.include_router(payroll_adjustments_router)",
        "app.include_router(payroll_adjustments_router)\n" + inc,
    )

path.write_text(text)
print("Payroll recalculation router enabled.")
