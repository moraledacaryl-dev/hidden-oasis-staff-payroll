#!/usr/bin/env python3
"""Smoke-test the Staff Payroll FastAPI wrapper.

Run the API first:
    python3 -m uvicorn api.server_review:app --host 127.0.0.1 --port 8001

Then run:
    python3 scripts/test_api_wrapper.py --start 2026-06-01 --end 2026-06-15

If STAFF_PAYROLL_API_KEY is configured in the API process, pass it here too:
    python3 scripts/test_api_wrapper.py --api-key change-this-before-production --start 2026-06-01 --end 2026-06-15
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8001"


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, api_key: str | None = None) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["X-API-Key"] = api_key

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} for {url}\n{body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not connect to {url}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Staff Payroll API wrapper.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--start", required=True, help="Payroll period start, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Payroll period end, YYYY-MM-DD")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    health = request_json("GET", f"{base}/health", api_key=args.api_key)
    print("Health:", health)

    meta = request_json("GET", f"{base}/api/v1/meta", api_key=args.api_key)
    print("Meta:", json.dumps(meta, indent=2))

    preview = request_json(
        "POST",
        f"{base}/api/v1/payroll/preview",
        payload={"period_start": args.start, "period_end": args.end},
        api_key=args.api_key,
    )
    print("Payroll preview summary:", preview.get("summary"))
    print("Payroll preview totals:", json.dumps(preview.get("totals"), indent=2))
    print("Preview mode:", preview.get("mode"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
