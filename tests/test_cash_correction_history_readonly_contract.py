from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORRECTIONS = ROOT / "api" / "cash_advance_corrections.py"
SERVER = ROOT / "api" / "server.py"


class CashCorrectionHistoryReadonlyContractTests(unittest.TestCase):
    @staticmethod
    def _between(source: str, start: str, end: str | None = None) -> str:
        block = source.split(start, 1)[1]
        return block.split(end, 1)[0] if end else block

    def test_credit_settlement_history_get_does_not_initialize_schema(self) -> None:
        source = CORRECTIONS.read_text()
        block = self._between(
            source,
            '@router.get("/cash-advances/{cash_advance_id}/credit-settlements")',
            '@router.get("/cash-advances/{cash_advance_id}/amount-corrections")',
        )
        self.assertNotIn("ensure_correction_schema(conn)", block)
        self.assertNotIn("conn.commit()", block)
        self.assertNotIn("ALTER TABLE", block)
        self.assertNotIn("CREATE TABLE", block)

    def test_amount_correction_history_get_does_not_initialize_schema(self) -> None:
        source = CORRECTIONS.read_text()
        block = self._between(
            source,
            '@router.get("/cash-advances/{cash_advance_id}/amount-corrections")',
        )
        self.assertNotIn("ensure_correction_schema(conn)", block)
        self.assertNotIn("conn.commit()", block)
        self.assertNotIn("ALTER TABLE", block)
        self.assertNotIn("CREATE TABLE", block)

    def test_write_paths_keep_defensive_schema_initialization(self) -> None:
        source = CORRECTIONS.read_text()
        correction = self._between(
            source,
            '@router.post("/cash-advances/{cash_advance_id}/correct-amount")',
            '@router.post("/cash-advances/{cash_advance_id}/settle-credit")',
        )
        settlement = self._between(
            source,
            '@router.post("/cash-advances/{cash_advance_id}/settle-credit")',
            '@router.get("/cash-advances/{cash_advance_id}/credit-settlements")',
        )
        self.assertIn("ensure_correction_schema(conn)", correction)
        self.assertIn("conn.commit()", correction)
        self.assertIn("ensure_correction_schema(conn)", settlement)
        self.assertIn("conn.commit()", settlement)

    def test_runtime_startup_owns_correction_schema(self) -> None:
        source = SERVER.read_text()
        self.assertIn(
            "from api.cash_advance_corrections import ensure_correction_schema",
            source,
        )
        init = self._between(source, "def initialize_runtime()", "@asynccontextmanager")
        self.assertIn("ensure_correction_schema(conn)", init)


if __name__ == "__main__":
    unittest.main()
