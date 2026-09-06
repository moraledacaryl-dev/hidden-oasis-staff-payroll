from __future__ import annotations

import inspect
import unittest

import api.server as server
import api.staff_self_service as staff_self_service


class ShiftRequestReadonlyContractTests(unittest.TestCase):
    def assert_read_only(self, fn) -> None:
        source = inspect.getsource(fn)
        self.assertNotIn("ensure_schema(conn)", source)
        self.assertNotIn("commit(", source)
        self.assertNotIn("ALTER TABLE", source.upper())
        self.assertNotIn("CREATE TABLE", source.upper())
        self.assertNotIn("CREATE INDEX", source.upper())

    def test_staff_self_service_read_is_side_effect_free(self) -> None:
        self.assert_read_only(staff_self_service.my_self_service)

    def test_reviewer_list_read_is_side_effect_free(self) -> None:
        self.assert_read_only(staff_self_service.list_shift_change_requests)

    def test_reviewer_detail_read_is_side_effect_free(self) -> None:
        self.assert_read_only(staff_self_service.get_shift_change_request)

    def test_startup_owns_shift_request_schema(self) -> None:
        source = inspect.getsource(server.initialize_runtime)
        self.assertIn("ensure_attachment_schema(conn)", source)

    def test_write_paths_keep_defensive_schema_initialization(self) -> None:
        for fn in (
            staff_self_service.submit_shift_change_request,
            staff_self_service.withdraw_shift_change_request,
            staff_self_service.confirm_shift_swap,
            staff_self_service.decline_shift_swap,
            staff_self_service.decide_shift_change_request,
        ):
            self.assertIn("ensure_schema(conn)", inspect.getsource(fn))


if __name__ == "__main__":
    unittest.main()
