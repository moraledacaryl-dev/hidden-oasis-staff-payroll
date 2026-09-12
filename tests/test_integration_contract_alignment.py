from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = runpy.run_path(str(ROOT / "scripts" / "verify_integration_pass3.py"))


class IntegrationContractAlignmentTests(unittest.TestCase):
    def test_operations_canary_uses_v2_receiver(self):
        endpoint = VERIFY["DESTINATIONS"]["operations"][2]
        self.assertEqual(
            endpoint,
            "/api/integrations/v2/events/hidden_oasis_staff_payroll",
        )

    def test_canary_staff_identity_uses_integer_source_id(self):
        payload = VERIFY["_payload"]("0123456789abcdef0123456789abcdef")
        employee = payload["payload"]["employees"][0]
        self.assertIsInstance(payload["source_record_id"], int)
        self.assertGreater(payload["source_record_id"], 0)
        self.assertEqual(employee["source_staff_id"], payload["source_record_id"])

    def test_operations_canary_is_translated_to_v2_envelope(self):
        payload = VERIFY["_payload"]("fedcba9876543210fedcba9876543210")
        outbound = VERIFY["_payload_for_destination"]("operations", payload)
        self.assertEqual(outbound["event_type"], "employee.status.changed")
        self.assertEqual(outbound["metadata"]["external_source"], "hidden_oasis_staff_payroll")
        self.assertEqual(outbound["metadata"]["original_event_type"], "employee.sync")
        self.assertEqual(outbound["subject"]["type"], "Employee")
        self.assertEqual(outbound["subject"]["id"], str(payload["source_record_id"]))

    def test_non_operations_destinations_keep_staff_envelope(self):
        payload = VERIFY["_payload"]("11111111111111111111111111111111")
        self.assertIs(VERIFY["_payload_for_destination"]("inventory", payload), payload)
        self.assertIs(VERIFY["_payload_for_destination"]("pos", payload), payload)
        self.assertIs(VERIFY["_payload_for_destination"]("accounting", payload), payload)

    def test_all_integration_processors_use_v2_aware_dispatcher(self):
        for relative_path in (
            "scripts/run_integration_worker.py",
            "scripts/process_integration_events.py",
            "api/integrations.py",
        ):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("from core.operations_v2_adapter import process_due_events", source)
            self.assertNotIn(
                "from core.integration_outbox import ensure_integration_schema, process_due_events",
                source,
            )


if __name__ == "__main__":
    unittest.main()
