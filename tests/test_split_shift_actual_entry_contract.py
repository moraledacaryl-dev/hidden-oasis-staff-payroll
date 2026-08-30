from pathlib import Path
import unittest


class SplitShiftActualEntryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Path("apps/web/components/ScheduleDayEditorModal.tsx").read_text(encoding="utf-8")

    def test_existing_shift_opens_on_actual_tab(self) -> None:
        self.assertIn('setTab(shift?.id && shift.id > 0 ? "actual" : initialTab);', self.source)

    def test_actual_form_waits_for_shift_linked_record(self) -> None:
        self.assertIn('loading && tab === "actual"', self.source)
        self.assertIn('!loading && tab === "actual"', self.source)
        self.assertIn('key={bundle.actual?.id ?? `new-actual-${currentShift.id}`}', self.source)

    def test_split_shift_copy_is_explicit_in_ui(self) -> None:
        self.assertIn('Actual attendance is stored for this specific shift only.', self.source)
        self.assertIn('Other shifts on the same date are recorded separately.', self.source)
        self.assertIn('Edit this shift actual', self.source)

    def test_actual_save_remains_linked_to_exact_shift_id(self) -> None:
        self.assertIn('shift_id: currentShift.id,', self.source)


if __name__ == "__main__":
    unittest.main()
