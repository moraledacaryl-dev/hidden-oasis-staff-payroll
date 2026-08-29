from __future__ import annotations

import unittest
from pathlib import Path


class P2AccessibilityContractTests(unittest.TestCase):
    def test_user_management_row_selects_have_accessible_names(self) -> None:
        source = Path("apps/web/components/UserManagementClient.tsx").read_text(encoding="utf-8")

        self.assertIn('aria-label={`Role for ${user.display_name}`}', source)
        self.assertIn('aria-label={`Employee linked to ${user.display_name}`}', source)

    def test_workspace_chrome_does_not_render_placeholder_search_or_notifications(self) -> None:
        source = Path("apps/web/components/WorkspaceChrome.tsx").read_text(encoding="utf-8")

        self.assertNotIn('aria-label="Search shortcut"', source)
        self.assertNotIn('aria-label="Notifications"', source)
        self.assertNotIn('Search staff, payroll, requests', source)
        self.assertNotIn('<kbd>⌘ K</kbd>', source)
        self.assertNotIn('Bell,', source)
        self.assertNotIn('Search,', source)

    def test_browser_smoke_understands_current_responsive_surfaces(self) -> None:
        source = Path("apps/web/scripts/browser-smoke.mjs").read_text(encoding="utf-8")

        self.assertIn('style.overflowX === "auto" || style.overflowX === "scroll"', source)
        self.assertIn("isHiddenOffCanvas", source)
        self.assertIn('rect.right <= 0 || rect.left >= window.innerWidth', source)
        self.assertIn("isHiddenOffCanvas(element)", source)

    def test_browser_smoke_uses_current_cutoff_and_schedule_contracts(self) -> None:
        source = Path("apps/web/scripts/browser-smoke.mjs").read_text(encoding="utf-8")

        self.assertIn('[data-cutoff-start="true"]', source)
        self.assertIn('[data-cutoff-end="true"]', source)
        self.assertIn('[data-payroll-payout-date="true"]', source)
        self.assertNotIn("input[name=\"month\"]", source)
        self.assertNotIn("select[name=\"half\"]", source)
        self.assertIn("document.querySelector('[draggable=\"true\"]')", source)
        self.assertIn("document.querySelectorAll('[data-schedule-cell]')", source)
        self.assertNotIn("data-drop-enabled", source)


if __name__ == "__main__":
    unittest.main()
