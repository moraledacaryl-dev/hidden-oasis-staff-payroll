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


if __name__ == "__main__":
    unittest.main()
