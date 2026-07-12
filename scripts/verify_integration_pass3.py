from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

DESTINATIONS = {
    "accounting": (
        "STAFF_PAYROLL_ACCOUNTING_SYNC_URL",
        "STAFF_PAYROLL_ACCOUNTING_SYNC_TOKEN",
        "/api/integrations/payroll/employees",
    ),
    "operations": (
        "STAFF_PAYROLL_OPERATIONS_SYNC_URL",
        "STAFF_PAYROLL_OPERATIONS_SYNC_TOKEN",
        "/api/integrations/staff/events",
    ),
    "pos": (
        "STAFF_PAYROLL_POS_SYNC_URL",
        "STAFF_PAYROLL_POS_SYNC_TOKEN",
        "/api/integrations/staff/employees",
    ),
    "inventory": (
        "STAFF_PAYROLL_INVENTORY_SYNC_URL",
        "STAFF_PAYROLL_INVENTORY_SYNC_TOKEN",
        "/api/v1/integrations/staff/employees",
    ),
}

SAFE_EMPLOYEE_FIELDS = {
    "employee_code",
    "display_name",
    "department",
    "position",
    "role",
    "active",
    "primary_department",
    "source_staff_id",
}


def _join(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _post(url: str, payload: dict[str, Any], token: str, timeout: int) -> tuple[int, str]:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Integration-Api-Key": token,
            "X-Integration-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def _payload(run_id: str) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    employee = {
        "employee_code": f"INT-CANARY-{run_id[-8:]}",
        "display_name": "Integration Canary",
        "department": "System",
        "position": "Integration Check",
        "role": "Canary",
        "active": False,
        "primary_department": "System",
        "source_staff_id": f"canary:{run_id}",
    }
    assert set(employee) <= SAFE_EMPLOYEE_FIELDS
    return {
        "external_source": "hidden_oasis_staff_payroll",
        "external_id": f"integration-pass3-canary:{run_id}",
        "event_type": "employee.sync",
        "source_record_type": "Employee",
        "source_record_id": f"canary:{run_id}",
        "generated_at": generated_at,
        "schema_version": "2026-06-v1",
        "payload": {
            "employees": [employee],
            "privacy_note": "Synthetic inactive identity used only for integration verification.",
        },
    }


def _decode(body: str) -> dict[str, Any]:
    try:
        value = json.loads(body or "{}")
    except json.JSONDecodeError:
        return {"raw": body[:1000]}
    return value if isinstance(value, dict) else {"value": value}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a safe employee-reference canary against configured Staff integration receivers."
    )
    parser.add_argument("--execute", action="store_true", help="Actually send the canary requests.")
    parser.add_argument(
        "--confirm",
        default="",
        help='Required with --execute. Must equal "PASS3 CANARY".',
    )
    parser.add_argument("--destination", action="append", choices=sorted(DESTINATIONS))
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    selected = args.destination or list(DESTINATIONS)
    configured: list[dict[str, str]] = []
    missing: list[str] = []
    for destination in selected:
        url_env, token_env, endpoint = DESTINATIONS[destination]
        base = os.getenv(url_env, "").strip()
        token = os.getenv(token_env, "").strip()
        if not base or not token:
            missing.append(destination)
            continue
        configured.append({
            "destination": destination,
            "url": _join(base, endpoint),
            "token_env": token_env,
        })

    if not args.execute:
        print(json.dumps({
            "mode": "plan_only",
            "configured": [{"destination": row["destination"], "url": row["url"]} for row in configured],
            "missing": missing,
            "note": "No requests were sent. Use --execute --confirm 'PASS3 CANARY' after receiver deployment.",
        }, indent=2))
        return 0

    if args.confirm != "PASS3 CANARY":
        print("Refusing to send requests: --confirm must equal PASS3 CANARY", file=sys.stderr)
        return 2
    if missing:
        print(json.dumps({"error": "destinations_not_configured", "destinations": missing}, indent=2), file=sys.stderr)
        return 2

    run_id = uuid.uuid4().hex
    payload = _payload(run_id)
    results: list[dict[str, Any]] = []
    failed = False
    for row in configured:
        token = os.environ[row["token_env"]].strip()
        first_status, first_body = _post(row["url"], payload, token, max(1, args.timeout))
        second_status, second_body = _post(row["url"], payload, token, max(1, args.timeout))
        bad_status, bad_body = _post(row["url"], payload, f"invalid-{run_id}", max(1, args.timeout))
        first_data = _decode(first_body)
        second_data = _decode(second_body)
        duplicate_ok = second_status in {200, 201, 409} and (
            second_status == 409
            or str(second_data.get("status", "")).lower().replace(" ", "_") in {"accepted", "already_applied"}
        )
        accepted = first_status in {200, 201} and str(first_data.get("status", "accepted")).lower().replace(" ", "_") in {
            "accepted",
            "already_applied",
        }
        auth_rejected = bad_status in {401, 403, 503}
        ok = accepted and duplicate_ok and auth_rejected
        failed = failed or not ok
        results.append({
            "destination": row["destination"],
            "url": row["url"],
            "accepted": accepted,
            "first_status": first_status,
            "first_response": first_data,
            "duplicate_safe": duplicate_ok,
            "second_status": second_status,
            "second_response": second_data,
            "invalid_secret_rejected": auth_rejected,
            "invalid_secret_status": bad_status,
            "invalid_secret_response": _decode(bad_body),
            "ok": ok,
        })

    report = {
        "mode": "executed",
        "run_id": run_id,
        "external_id": payload["external_id"],
        "safe_employee_fields": sorted(SAFE_EMPLOYEE_FIELDS),
        "results": results,
        "ok": not failed,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
