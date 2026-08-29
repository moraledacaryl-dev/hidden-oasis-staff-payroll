from __future__ import annotations

import unittest
from pathlib import Path


class ProductionPreflightCwdTests(unittest.TestCase):
    def test_python_compile_runs_from_repository_root(self) -> None:
        source = Path("scripts/production_preflight.py").read_text(encoding="utf-8")

        self.assertIn("ROOT = Path(__file__).resolve().parents[1]", source)
        self.assertIn("cwd=ROOT", source)
        self.assertIn('"api/server.py"', source)
        self.assertIn('"scripts/restore_drill.py"', source)


if __name__ == "__main__":
    unittest.main()
