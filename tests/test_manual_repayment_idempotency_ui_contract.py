from pathlib import Path
import unittest


class ManualRepaymentIdempotencyUIContract(unittest.TestCase):
    def test_form_keeps_id_stable_on_uncertain_retries(self) -> None:
        source = Path("apps/web/components/ManualRepaymentForm.tsx").read_text(encoding="utf-8")
        self.assertIn("useRef", source)
        self.assertIn("crypto.randomUUID()", source)
        self.assertIn("pendingRequest.current.fingerprint !== fingerprint", source)
        self.assertIn("idempotency_key: pendingRequest.current.key", source)
        self.assertIn("Could not confirm the result.", source)
        self.assertIn("pendingRequest.current = null;", source)
        self.assertIn("disabled={busy}", source)

    def test_backend_uses_serialized_balance_guard_and_unique_index(self) -> None:
        endpoint = Path("api/cash_repayments.py").read_text(encoding="utf-8")
        schema = Path("api/cash_advance_service.py").read_text(encoding="utf-8")
        self.assertIn('conn.execute("BEGIN IMMEDIATE")', endpoint)
        self.assertIn('WHERE idempotency_key=?', endpoint)
        self.assertIn('"already_recorded": True', endpoint)
        self.assertIn("uq_ca_manual_idempotency", schema)


if __name__ == "__main__":
    unittest.main()
