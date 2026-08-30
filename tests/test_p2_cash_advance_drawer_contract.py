from __future__ import annotations

import unittest
from pathlib import Path


class P2CashAdvanceDrawerContractTests(unittest.TestCase):
    def test_existing_advance_editor_uses_canonical_drawer(self) -> None:
        source = Path("apps/web/components/CashAdvanceFormV2.tsx").read_text(encoding="utf-8")

        self.assertIn('import { AppDrawer } from "@/components/AppSurface";', source)
        self.assertIn('<AppDrawer', source)
        self.assertIn('title="Update advance details"', source)
        self.assertIn('open={open}', source)
        self.assertIn('onClose={() => { if (!busy) setOpen(false); }}', source)
        self.assertIn('if (!open) return <button className="button small"', source)

    def test_new_advance_form_remains_inline(self) -> None:
        source = Path("apps/web/components/CashAdvanceFormV2.tsx").read_text(encoding="utf-8")

        self.assertIn('const renderForm = () => (', source)
        self.assertIn('if (!item) return renderForm();', source)

    def test_drawer_preserves_balance_and_lifecycle_safeguards(self) -> None:
        source = Path("apps/web/components/CashAdvanceFormV2.tsx").read_text(encoding="utf-8")

        self.assertIn('amount: item ? currentBasis : amount', source)
        self.assertIn('disabled={Boolean(item)}', source)
        self.assertIn('Owners must use the separate Correct balance basis action.', source)
        self.assertIn('if (["reject", "cancel"].includes(action) && !actionReason.trim())', source)
        self.assertIn('body: JSON.stringify({ action, cash_advance_id: item.id, reason: actionReason.trim() || null })', source)

    def test_mobile_drawer_is_full_viewport(self) -> None:
        source = Path("apps/web/app/pass1-surfaces.css").read_text(encoding="utf-8")

        self.assertIn('@media(max-width:620px)', source)
        self.assertIn('.app-drawer{width:100vw;border-left:0}', source)
        self.assertIn('height:100dvh', source)


if __name__ == "__main__":
    unittest.main()
