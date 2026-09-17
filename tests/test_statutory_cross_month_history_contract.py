from __future__ import annotations

from pathlib import Path


def test_cross_month_history_must_not_drop_prior_cross_month_run() -> None:
    source = Path("core/statutory_history.py").read_text(encoding="utf-8")
    # A prior Aug31-Sep14 run contributes September statutory history to a
    # Sep30-Oct14 run even though its period_start is in August.  Filtering
    # history by `pr.period_start >= month_start` silently drops that basis.
    assert "pr.period_start >= ?" not in source


def test_statutory_history_has_month_snapshot_source() -> None:
    source = Path("core/statutory_history.py").read_text(encoding="utf-8")
    assert "payroll_statutory_months" in source
