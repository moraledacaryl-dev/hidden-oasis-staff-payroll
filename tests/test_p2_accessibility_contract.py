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

    def test_shared_page_grid_track_is_shrinkable(self) -> None:
        layout = Path("apps/web/app/layout.tsx").read_text(encoding="utf-8")
        source = Path("apps/web/app/responsive-grid-track.css").read_text(encoding="utf-8")

        self.assertIn('import "./responsive-grid-track.css";', layout)
        self.assertIn(".page", source)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", source)

    def test_schedule_mobile_shell_can_shrink_inside_viewport(self) -> None:
        source = Path("apps/web/app/schedule/page.module.css").read_text(encoding="utf-8")

        self.assertIn(".page{width:auto;max-width:100%;min-width:0", source)
        self.assertIn(".pageHeading{", source)
        self.assertIn("min-width:0;max-width:100%", source)
        self.assertIn(".headingActions{", source)
        self.assertIn(".kpiGrid{", source)
        self.assertIn("grid-template-columns:minmax(0,1fr)", source)
        self.assertIn("overflow-wrap:anywhere", source)

    def test_schedule_mobile_publication_control_uses_full_shrinkable_row(self) -> None:
        source = Path("apps/web/app/schedule/page.module.css").read_text(encoding="utf-8")

        self.assertIn(".controlsCard{min-width:0;max-width:100%", source)
        self.assertIn(".controlsHead{", source)
        self.assertIn(".controlsHead>*{min-width:0;max-width:100%}", source)
        self.assertIn("grid-template-columns:minmax(0,1fr) minmax(0,1fr)", source)
        self.assertIn(".publishInline{grid-column:1/-1;width:100%}", source)
        self.assertIn(".publishInline :global(.card){width:100%}", source)

    def test_staff_portal_mobile_shell_can_shrink_inside_viewport(self) -> None:
        source = Path("apps/web/app/staff-portal.css").read_text(encoding="utf-8")

        self.assertIn(".staff-portal{width:auto;max-width:100%;min-width:0", source)
        self.assertIn(".staff-hero{", source)
        self.assertIn(".staff-hero>div{min-width:0;max-width:100%}", source)
        self.assertIn(".staff-summary{display:grid;width:auto;max-width:100%;min-width:0", source)
        self.assertIn(".staff-summary-card{min-width:0;max-width:100%", source)
        self.assertIn("grid-template-columns:minmax(0,1fr)", source)
        self.assertIn("overflow-wrap:anywhere", source)


if __name__ == "__main__":
    unittest.main()
