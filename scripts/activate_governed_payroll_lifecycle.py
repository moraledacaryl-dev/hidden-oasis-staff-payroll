from __future__ import annotations

from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "api" / "server_review.py"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    updated = text.replace(
        "from api.payroll_drafts import router as payroll_drafts_router",
        "from api.payroll_drafts_v2 import router as payroll_drafts_router",
    ).replace(
        "from api.payroll_revision_workflow_v2 import router as revision_workflow_router",
        "from api.payroll_revision_workflow_v3 import router as revision_workflow_router",
    )

    if updated == text:
        print("No changes were needed; governed payroll lifecycle is already active.")
        return

    TARGET.write_text(updated, encoding="utf-8")
    print(f"Updated {TARGET}")
    print("Activated payroll_drafts_v2 and payroll_revision_workflow_v3.")


if __name__ == "__main__":
    main()
