from __future__ import annotations

from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "api" / "server_review.py"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    updated = text

    import_line = "from api.schedule_rest_days import router as schedule_rest_days_router"
    if import_line not in updated:
        anchor = "from api.schedule_actuals import router as schedule_actuals_router"
        if anchor not in updated:
            raise RuntimeError("Could not find schedule_actuals import anchor in api/server_review.py")
        updated = updated.replace(anchor, f"{anchor}\n{import_line}")

    include_line = "app.include_router(schedule_rest_days_router)"
    if include_line not in updated:
        anchor = "app.include_router(schedule_actuals_router)"
        if anchor not in updated:
            raise RuntimeError("Could not find schedule_actuals router anchor in api/server_review.py")
        updated = updated.replace(anchor, f"{anchor}\n{include_line}")

    if updated == text:
        print("Schedule rest-day router is already active.")
        return

    TARGET.write_text(updated, encoding="utf-8")
    print(f"Updated {TARGET}")
    print("Activated schedule_rest_days router.")


if __name__ == "__main__":
    main()
