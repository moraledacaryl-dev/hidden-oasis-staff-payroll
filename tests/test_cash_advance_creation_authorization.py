from __future__ import annotations

import pytest
from fastapi import HTTPException

from api import cash_advance_service as service


def _user(role_key: str) -> dict[str, str]:
    return {"role_key": role_key, "display_name": role_key.title()}


def test_supervisor_remains_viewer_but_cannot_create_cash_advance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "current_user_from_token", lambda _authorization: _user("supervisor"))

    viewer = service.require_cash_advance_viewer("Bearer supervisor", None)
    assert viewer["role_key"] == "supervisor"

    with pytest.raises(HTTPException) as exc_info:
        service.require_cash_advance_creator("Bearer supervisor", None)

    assert exc_info.value.status_code == 403


@pytest.mark.parametrize("role_key", ["owner", "payroll"])
def test_financial_roles_can_create_cash_advances(monkeypatch: pytest.MonkeyPatch, role_key: str) -> None:
    monkeypatch.setattr(service, "current_user_from_token", lambda _authorization: _user(role_key))

    user = service.require_cash_advance_creator(f"Bearer {role_key}", None)

    assert user["role_key"] == role_key


def test_api_key_system_creation_remains_payroll_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "require_api_key", lambda _api_key: None)

    user = service.require_cash_advance_creator(None, "integration-key")

    assert user["role_key"] == "payroll"
