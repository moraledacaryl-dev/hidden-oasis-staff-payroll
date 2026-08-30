from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TimezoneContractTests(unittest.TestCase):
    def test_no_naive_wall_clock_now_in_api_or_core(self) -> None:
        offenders: list[str] = []
        patterns = (
            re.compile(r"datetime\.now\(\)"),
            re.compile(r"datetime\.utcnow\(\)"),
        )
        for base in (ROOT / "api", ROOT / "core"):
            for path in base.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for pattern in patterns:
                    for match in pattern.finditer(text):
                        line = text.count("\n", 0, match.start()) + 1
                        offenders.append(f"{path.relative_to(ROOT)}:{line}: {match.group(0)}")
        self.assertEqual([], offenders, "Naive wall-clock timestamps remain:\n" + "\n".join(offenders))

    def test_utc_storage_and_manila_business_helpers_exist(self) -> None:
        observability = (ROOT / "core" / "observability.py").read_text(encoding="utf-8")
        self.assertIn('ZoneInfo("Asia/Manila")', observability)
        self.assertIn("def utc_storage_iso", observability)
        self.assertIn("def manila_now", observability)
        self.assertIn("def manila_today", observability)

    def test_database_timestamp_writer_is_aware_utc(self) -> None:
        db = (ROOT / "core" / "db.py").read_text(encoding="utf-8")
        self.assertIn("from .observability import utc_storage_iso", db)
        self.assertIn("return utc_storage_iso()", db)
        self.assertNotIn("return datetime.now().replace", db)

    def test_login_lockout_accepts_legacy_and_aware_values(self) -> None:
        source = (ROOT / "core" / "login_security.py").read_text(encoding="utf-8")
        self.assertIn("parse_timestamp_utc", source)
        self.assertIn("utc_now", source)
        self.assertIn("utc_storage_iso", source)
        self.assertNotIn("locked_until - datetime.now()", source)

    def test_api_normalizes_timestamp_fields_with_offsets(self) -> None:
        source = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
        self.assertIn("normalize_api_timestamp", source)
        self.assertIn("key.endswith(\"_at\")", source)
        self.assertIn("parse_timestamp_utc", source)
        self.assertIn("utc_iso", source)

    def test_operational_timestamp_writers_do_not_use_local_time(self) -> None:
        for relative in (
            "core/backups.py",
            "core/integration_outbox.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("datetime.now()", source, relative)
            self.assertNotIn("datetime.fromtimestamp(path.stat().st_mtime)", source, relative)


if __name__ == "__main__":
    unittest.main()
