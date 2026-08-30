from __future__ import annotations

import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.observability import normalize_request_id, parse_timestamp_utc, utc_iso


ROOT = Path(__file__).resolve().parents[1]


class ProductionObservabilityContractTests(unittest.TestCase):
    def test_utc_iso_serializes_explicit_utc_instant(self) -> None:
        value = datetime(2026, 8, 30, 15, 30, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(utc_iso(value), "2026-08-30T07:30:00Z")

    def test_parser_accepts_legacy_naive_and_aware_timestamps(self) -> None:
        legacy = parse_timestamp_utc("2026-08-30 07:30:00")
        aware = parse_timestamp_utc("2026-08-30T15:30:00+08:00")
        self.assertEqual(legacy.tzinfo, timezone.utc)
        self.assertEqual(legacy, aware)

    def test_request_id_reuses_only_safe_bounded_values(self) -> None:
        self.assertEqual(normalize_request_id("probe-123_A"), "probe-123_A")
        generated = normalize_request_id("bad request id with spaces")
        self.assertRegex(generated, re.compile(r"^[0-9a-f]{32}$"))
        self.assertNotEqual(generated, "bad request id with spaces")

    def test_production_health_is_non_cacheable_correlated_and_utc_safe(self) -> None:
        source = (ROOT / "api" / "production_health.py").read_text()
        self.assertIn('response.headers["Cache-Control"] = "no-store, max-age=0"', source)
        self.assertIn('response.headers["Pragma"] = "no-cache"', source)
        self.assertIn('response.headers["X-Request-ID"] = request_id', source)
        self.assertIn('"checked_at": utc_iso()', source)
        self.assertIn('"request_id": request_id', source)
        self.assertIn("parse_timestamp_utc(created_at)", source)
        self.assertNotIn("datetime.now() - created", source)


if __name__ == "__main__":
    unittest.main()
