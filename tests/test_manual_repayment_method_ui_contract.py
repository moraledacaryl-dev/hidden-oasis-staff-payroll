from pathlib import Path
import unittest


class ManualRepaymentMethodUiContractTests(unittest.TestCase):
    def test_manual_repayment_form_requires_real_payment_method(self) -> None:
        source = Path("apps/web/components/ManualRepaymentForm.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('name="payment_method" defaultValue="" required', source)
        self.assertIn('value="" disabled>Select actual method', source)
        self.assertIn("<option>Cash</option>", source)
        self.assertIn("<option>GCash</option>", source)
        self.assertIn("<option>Bank transfer</option>", source)
        self.assertIn("<option>Maya</option>", source)
        self.assertIn('payment_method: paymentMethod', source)
        self.assertNotIn('payment_method: String(formData.get("payment_method") || "Cash")', source)
        self.assertNotIn('defaultValue="Cash"', source)


if __name__ == "__main__":
    unittest.main()
