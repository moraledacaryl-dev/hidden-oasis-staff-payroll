from __future__ import annotations

from unittest.mock import patch

import api.schedule_history_controls as history


def test_legacy_actual_handler_delegates_to_canonical_shift_writer() -> None:
    payload = object()
    captured = {}

    def fake_canonical(actual_payload, authorization, x_api_key):
        captured["payload"] = actual_payload
        captured["authorization"] = authorization
        captured["x_api_key"] = x_api_key
        return {"ok": True, "actual": {"scheduled_shift_id": 1298}}

    with patch.object(history, "canonical_save_day_actual", fake_canonical):
        result = history.save_actual_history(payload, "Bearer token", "api-key")

    assert captured == {
        "payload": payload,
        "authorization": "Bearer token",
        "x_api_key": "api-key",
    }
    assert result["actual"]["scheduled_shift_id"] == 1298
